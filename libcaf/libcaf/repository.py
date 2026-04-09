"""libcaf repository management."""

from contextlib import ExitStack
import os
import shutil
import tempfile
import uuid
from pathlib import Path
from collections import deque
from collections.abc import Callable, Generator, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from functools import wraps
from typing import Concatenate, Optional, Tuple
from . import Blob, Commit, Tree, TreeRecord, TreeRecordType
from .constants import (DEFAULT_BRANCH, DEFAULT_REPO_DIR, HASH_CHARSET, HASH_LENGTH, HEADS_DIR, HEAD_FILE,
                        OBJECTS_SUBDIR, REFS_DIR, TAGS_DIR, MERGE_HEAD_FILE)
from .plumbing import hash_object, load_commit, load_tree, save_commit, save_file_content, save_tree, hash_file, restore_blob_to_path
from .ref import HashRef, Ref, RefError, SymRef, read_ref, write_ref, coerce_to_ref
from libcaf.merge_algo import MergeConflict, find_lca, merge_trees, compute_merge_tree, is_binary_blob, three_way_merge
from libcaf.sequences import prepare_lines_sequence
from enum import Enum, auto



class RepositoryError(Exception):
    """Exception raised for repository-related errors."""


class RepositoryNotFoundError(RepositoryError):
    """Exception raised when a repository is not found."""

class MergeResult(Enum):
    UP_TO_DATE = auto()
    FAST_FORWARD = auto()
    MERGE_CREATED = auto()
    CONFLICTS = auto()

@dataclass
class MergeReport:
    status: MergeResult
    commit_hash: Optional[HashRef] = None
    # 'clean_updates' holds paths mapping to blob hashes. 
    # This includes 3-way auto-merges, brand new files, AND files updated cleanly by the source branch.
    clean_updates: dict[str, TreeRecord] = field(default_factory=dict)
    # Files that the source branch safely deleted
    deletions: list[str] = field(default_factory=list)
    conflicts: list[tuple[str, MergeConflict]] = field(default_factory=list)

@dataclass
class Diff:
    """A class representing a difference between two tree records."""

    record: TreeRecord
    parent: 'Diff | None'
    children: list['Diff']


@dataclass
class AddedDiff(Diff):
    """An added tree record diff as part of a commit."""


@dataclass
class RemovedDiff(Diff):
    """A removed tree record diff as part of a commit."""


@dataclass
class ModifiedDiff(Diff):
    """A modified tree record diff as part of a commit."""


@dataclass
class MovedToDiff(Diff):
    """A tree record diff that has been moved elsewhere as part of a commit."""

    moved_to: 'MovedFromDiff | None'


@dataclass
class MovedFromDiff(Diff):
    """A tree record diff that has been moved from elsewhere as part of a commit."""

    moved_from: MovedToDiff | None


@dataclass
class LogEntry:
    """A class representing a log entry for a branch or commit history."""

    commit_ref: HashRef
    commit: Commit


class Repository:
    """Represents a libcaf repository.

    This class provides methods to initialize a repository, manage branches,
    commit changes, and perform various operations on the repository."""

    def __init__(self, working_dir: Path | str, repo_dir: Path | str | None = None) -> None:
        """Initialize a Repository instance. The repository is not created on disk until `init()` is called.

        :param working_dir: The working directory where the repository will be located.
        :param repo_dir: The name of the repository directory within the working directory. Defaults to '.caf'."""
        self.working_dir = Path(working_dir)

        if repo_dir is None:
            self.repo_dir = Path(DEFAULT_REPO_DIR)
        else:
            self.repo_dir = Path(repo_dir)

    def init(self, default_branch: str = DEFAULT_BRANCH) -> None:
        """Initialize a new CAF repository in the working directory.

        :param default_branch: The name of the default branch to create. Defaults to 'main'.
        :raises RepositoryError: If the repository already exists or if the working directory is invalid."""
        self.repo_path().mkdir(parents=True)
        self.objects_dir().mkdir()

        heads_dir = self.heads_dir()
        heads_dir.mkdir(parents=True)

        write_ref(self.head_file(), SymRef(f"heads/{default_branch}"))

    def exists(self) -> bool:
        """Check if the repository exists in the working directory.

        :return: True if the repository exists, False otherwise."""
        return self.repo_path().exists()

    def repo_path(self) -> Path:
        """Get the path to the repository directory.

        :return: The path to the repository directory."""
        return self.working_dir / self.repo_dir

    def objects_dir(self) -> Path:
        """Get the path to the objects directory within the repository.

        :return: The path to the objects directory."""
        return self.repo_path() / OBJECTS_SUBDIR

    def refs_dir(self) -> Path:
        """Get the path to the refs directory within the repository.

        :return: The path to the refs directory."""
        return self.repo_path() / REFS_DIR

    def heads_dir(self) -> Path:
        """Get the path to the heads directory within the repository.

        :return: The path to the heads directory."""
        return self.refs_dir() / HEADS_DIR

    @staticmethod
    def requires_repo[**P, R](func: Callable[Concatenate['Repository', P], R]) -> \
            Callable[Concatenate['Repository', P], R]:
        """Decorate a Repository method to ensure that the repository exists before executing the method.

        :param func: The method to decorate.
        :return: A wrapper function that checks for the repository's existence."""

        @wraps(func)
        def _verify_repo(self: 'Repository', *args: P.args, **kwargs: P.kwargs) -> R:
            if not self.exists():
                msg = f'Repository not initialized at {self.repo_path()}'
                raise RepositoryNotFoundError(msg)

            return func(self, *args, **kwargs)

        return _verify_repo

    @requires_repo
    def head_ref(self) -> Ref | None:
        """Get the current HEAD reference of the repository.

        :return: The current HEAD reference, which can be a HashRef or SymRef.
        :raises RepositoryError: If the HEAD ref file does not exist.
        :raises RepositoryNotFoundError: If the repository does not exist."""
        head_file = self.head_file()
        if not head_file.exists():
            msg = 'HEAD ref file does not exist'
            raise RepositoryError(msg)

        return read_ref(head_file)

    @requires_repo
    def head_commit(self) -> HashRef | None:
        """Return a ref to the current commit reference of the HEAD.

        :return: The current commit reference, or None if HEAD is not a commit.
        :raises RepositoryError: If the HEAD ref file does not exist.
        :raises RepositoryNotFoundError: If the repository does not exist."""
        # If HEAD is a symbolic reference, resolve it to a hash
        resolved_ref = self.resolve_ref(self.head_ref())
        if resolved_ref:
            return resolved_ref
        return None

    @requires_repo
    def refs(self) -> list[SymRef]:
        """Get a list of all symbolic references in the repository.

        :return: A list of SymRef objects representing the symbolic references.
        :raises RepositoryError: If the refs directory does not exist or is not a directory.
        :raises RepositoryNotFoundError: If the repository does not exist."""
        refs_dir = self.refs_dir()
        if not refs_dir.exists() or not refs_dir.is_dir():
            msg = f'Refs directory does not exist or is not a directory: {refs_dir}'
            raise RepositoryError(msg)

        refs: list[SymRef] = [SymRef(ref_file.name) for ref_file in refs_dir.rglob('*')
                              if ref_file.is_file()]

        return refs

    @requires_repo
    def resolve_ref(self, ref: Ref | str | None) -> HashRef | None:
        """Resolve a reference to a HashRef, following symbolic references if necessary.

        :param ref: The reference to resolve. This can be a HashRef, SymRef, or a string.
        :return: The resolved HashRef or None if the reference does not exist.
        :raises RefError: If the reference is invalid or cannot be resolved.
        :raises RepositoryNotFoundError: If the repository does not exist."""
        match ref:
            case HashRef():
                return ref
            case SymRef() as ref:
                if ref.upper() == 'HEAD':
                    return self.resolve_ref(self.head_ref())
                try:
                    resolved = read_ref(self.refs_dir() / ref)
                    return self.resolve_ref(resolved)
                except FileNotFoundError:
                    # The branch is "unborn" (or missing), so it points to nothing yet!
                    return None

            case str():
                # Try to figure out what kind of ref it is by looking at the list of refs
                # in the refs directory
                if ref.upper() == 'HEAD' or ref in self.refs():
                    return self.resolve_ref(SymRef(ref))
                if len(ref) == HASH_LENGTH and all(c in HASH_CHARSET for c in ref):
                    return HashRef(ref)

                msg = f'Invalid reference: {ref}'
                raise RefError(msg)
            case None:
                return None
            case _:
                msg = f'Invalid reference type: {type(ref)}'
                raise RefError(msg)

    @requires_repo
    def update_ref(self, ref_name: str, new_ref: Ref) -> None:
        """Update a symbolic reference in the repository.

        :param ref_name: The name of the symbolic reference to update.
        :param new_ref: The new reference value to set.
        :raises RepositoryError: If the reference does not exist.
        :raises RepositoryNotFoundError: If the repository does not exist."""
        ref_path = self.refs_dir() / ref_name

        if not ref_path.exists():
            msg = f'Reference "{ref_name}" does not exist.'
            raise RepositoryError(msg)

        write_ref(ref_path, new_ref)

    @requires_repo
    def delete_repo(self) -> None:
        """Delete the entire repository, including all objects and refs.

        :raises RepositoryNotFoundError: If the repository does not exist."""
        shutil.rmtree(self.repo_path())

    @requires_repo
    def save_file_content(self, file: Path) -> Blob:
        """Save the content of a file to the repository.

        :param file: The path to the file to save.
        :return: A Blob object representing the saved file content.
        :raises ValueError: If the file does not exist.
        :raises RepositoryNotFoundError: If the repository does not exist."""
        return save_file_content(self.objects_dir(), file)

    @requires_repo
    def add_branch(self, branch: str) -> None:
        """Add a new branch to the repository, pointing to the current HEAD commit.

        :param branch: The name of the branch to add.
        :raises ValueError: If the branch name is empty.
        :raises RepositoryError: If the branch already exists or the repo has no commits.
        :raises RepositoryNotFoundError: If the repository does not exist."""
        if not branch:
            msg = 'Branch name is required'
            raise ValueError(msg)
            
        if self.branch_exists(SymRef(branch)):
            msg = f'Branch "{branch}" already exists'
            raise RepositoryError(msg)

        current_hash = self.head_commit()
        if current_hash is None:
            # Prevent creating a branch in an empty repo
            raise RepositoryError(
                f"Cannot create branch '{branch}'. "
                "You must make your first commit before creating additional branches."
            )

        write_ref(self.heads_dir() / branch, HashRef(current_hash))

    @requires_repo
    def delete_branch(self, branch: str) -> None:
        """Delete a branch from the repository.

        :param branch: The name of the branch to delete.
        :raises ValueError: If the branch name is empty.
        :raises RepositoryError: If the branch does not exist or if it is the last branch in the repository.
        :raises RepositoryNotFoundError: If the repository does not exist."""
        if not branch:
            msg = 'Branch name is required'
            raise ValueError(msg)
        branch_path = self.heads_dir() / branch

        if not branch_path.exists():
            msg = f'Branch "{branch}" does not exist.'
            raise RepositoryError(msg)
        if len(self.branches()) == 1:
            msg = f'Cannot delete the last branch "{branch}".'
            raise RepositoryError(msg)

        branch_path.unlink()

    @requires_repo
    def branch_exists(self, branch_ref: Ref) -> bool:
        """Check if a branch exists in the repository.

        :param branch_ref: The reference to the branch to check.
        :return: True if the branch exists, False otherwise.
        :raises RepositoryNotFoundError: If the repository does not exist."""
        return (self.heads_dir() / branch_ref).exists()

    @requires_repo
    def branches(self) -> list[str]:
        """Get a list of all branch names in the repository.

        :return: A list of branch names.
        :raises RepositoryNotFoundError: If the repository does not exist."""
        return [x.name for x in self.heads_dir().iterdir() if x.is_file()]

    @requires_repo
    def save_dir(self, path: Path) -> HashRef:
        """Save the content of a directory to the repository.

        :param path: The path to the directory to save.
        :return: A HashRef object representing the saved directory tree object.
        :raises NotADirectoryError: If the path is not a directory.
        :raises RepositoryNotFoundError: If the repository does not exist."""
        if not path or not path.is_dir():
            msg = f'{path} is not a directory'
            raise NotADirectoryError(msg)

        stack = deque([path])
        hashes: dict[Path, str] = {}

        while stack:
            current_path = stack.pop()
            tree_records: dict[str, TreeRecord] = {}

            for item in current_path.iterdir():
                if item.name == self.repo_dir.name:
                    continue
                if item.is_file():
                    blob = self.save_file_content(item)
                    tree_records[item.name] = TreeRecord(TreeRecordType.BLOB, blob.hash, item.name)
                elif item.is_dir():
                    if item in hashes:  # If the directory has already been processed, use its hash
                        subtree_hash = hashes[item]
                        tree_records[item.name] = TreeRecord(TreeRecordType.TREE, subtree_hash, item.name)
                    else:
                        stack.append(current_path)
                        stack.append(item)
                        break
            else:
                tree = Tree(tree_records)
                save_tree(self.objects_dir(), tree)
                hashes[current_path] = hash_object(tree)

        return HashRef(hashes[path])

    @requires_repo
    def commit_working_dir(self, author: str, message: str) -> HashRef:
        """Commit the current working directory to the repository.

        :param author: The name of the commit author.
        :param message: The commit message.
        :return: A HashRef object representing the commit reference.
        :raises ValueError: If the author or message is empty.
        :raises RepositoryError: If the commit process fails or conflicts are unresolved.
        :raises RepositoryNotFoundError: If the repository does not exist."""
        if not author:
            msg = 'Author is required'
            raise ValueError(msg)
        if not message:
            msg = 'Commit message is required'
            raise ValueError(msg)

        head_ref = self.head_ref()
        branch = head_ref if isinstance(head_ref, SymRef) else None
        parent_commit_ref = self.head_commit()

        parents = [parent_commit_ref] if parent_commit_ref else []

        merge_head_file = self.merge_head_file()
        if merge_head_file.exists():
            for file_path in self.working_dir.rglob('*'):
                # Ignore the internal .caf directory
                if self.repo_dir.name in file_path.parts:
                    continue
                if not file_path.is_file():
                    continue

                # Check for structural conflict backups left behind
                if file_path.name.endswith('~HEAD') or file_path.name.endswith('~MERGE_HEAD'):
                    raise RepositoryError(
                        f'Cannot commit: Unresolved structural conflict backup file found ({file_path.name})'
                    )

                # Check for content conflict markers
                try:
                    # Stream the file line-by-line in binary to completely avoid MemoryError
                    with file_path.open('rb') as f:
                        for line in f:
                            if b'<<<<<<< HEAD' in line:
                                rel_path = file_path.relative_to(self.working_dir)
                                raise RepositoryError(f'Cannot commit: Unresolved conflict markers found in {rel_path}')
                except RepositoryError:
                    # Re-raise our own conflict error so it stops the commit
                    raise
                except OSError as e:
                    # If the OS locks the file, we cannot guarantee a clean merge.
                    rel_path = file_path.relative_to(self.working_dir)
                    raise RepositoryError(f'Cannot commit: Unable to verify conflict status of {rel_path} ({e})')

            merge_head_hash = read_ref(merge_head_file)
            if not isinstance(merge_head_hash, HashRef):
                raise RepositoryError('Cannot commit: Corrupt MERGE_HEAD file. Expected a valid commit hash.')
            parents.append(merge_head_hash)

        # Save the current working directory as a tree
        tree_hash = self.save_dir(self.working_dir)
        
        commit = Commit(tree_hash, author, message, int(datetime.now().timestamp()), parents)
        commit_ref = HashRef(hash_object(commit))

        save_commit(self.objects_dir(), commit)

        if branch:
            ref_path = self.refs_dir() / branch
            if not ref_path.exists():
                # This is the very first commit on an unborn branch!
                # We bypass update_ref (which expects it to exist) and create it directly.
                write_ref(ref_path, commit_ref)
            else:
                # Standard commit on an existing branch
                self.update_ref(branch, commit_ref)

        # clean up merge state
        if merge_head_file.exists():
            merge_head_file.unlink()

        return commit_ref

    @requires_repo
    def log(self, tip: Ref | None = None) -> Generator[LogEntry, None, None]:
        """Generate a log of commits in the repository, starting from the specified tip.

        :param tip: The reference to the commit to start from. If None, defaults to the current HEAD.
        :return: A generator yielding LogEntry objects representing the commits in the log.
        :raises RepositoryError: If a commit cannot be loaded.
        :raises RepositoryNotFoundError: If the repository does not exist."""
        tip = tip or self.head_ref()
        current_hash = self.resolve_ref(tip)

        try:
            while current_hash:
                commit = load_commit(self.objects_dir(), current_hash)
                yield LogEntry(HashRef(current_hash), commit)

                current_hash = HashRef(commit.parents[0]) if commit.parents else None
        except Exception as e:
            msg = f'Error loading commit {current_hash}'
            raise RepositoryError(msg) from e

    @requires_repo
    def diff_commits(self, commit_ref1: Ref | None = None, commit_ref2: Ref | None = None) -> Sequence[Diff]:
        """Generate a diff between two commits in the repository.

        :param commit_ref1: The reference to the first commit. If None, defaults to the current HEAD.
        :param commit_ref2: The reference to the second commit. If None, defaults to the current HEAD.
        :return: A list of Diff objects representing the differences between the two commits.
        :raises RepositoryError: If a commit or tree cannot be loaded.
        :raises RepositoryNotFoundError: If the repository does not exist."""
        if commit_ref1 is None:
            commit_ref1 = self.head_ref()
        if commit_ref2 is None:
            commit_ref2 = self.head_ref()

        try:
            commit_hash1 = self.resolve_ref(commit_ref1)
            commit_hash2 = self.resolve_ref(commit_ref2)

            if commit_hash1 is None:
                msg = f'Cannot resolve reference {commit_ref1}'
                raise RefError(msg)
            if commit_hash2 is None:
                msg = f'Cannot resolve reference {commit_ref2}'
                raise RefError(msg)

            commit1 = load_commit(self.objects_dir(), commit_hash1)
            commit2 = load_commit(self.objects_dir(), commit_hash2)
        except Exception as e:
            msg = 'Error loading commit'
            raise RepositoryError(msg) from e

        if commit1.tree_hash == commit2.tree_hash:
            return []

        try:
            tree1 = load_tree(self.objects_dir(), commit1.tree_hash)
            tree2 = load_tree(self.objects_dir(), commit2.tree_hash)
        except Exception as e:
            msg = 'Error loading tree'
            raise RepositoryError(msg) from e

        top_level_diff = Diff(TreeRecord(TreeRecordType.TREE, '', ''), None, [])
        stack = [(tree1, tree2, top_level_diff)]

        potentially_added: dict[str, Diff] = {}
        potentially_removed: dict[str, Diff] = {}

        while stack:
            current_tree1, current_tree2, parent_diff = stack.pop()
            records1 = current_tree1.records if current_tree1 else {}
            records2 = current_tree2.records if current_tree2 else {}

            for name, record1 in records1.items():
                if name not in records2:
                    local_diff: Diff

                    # This name is no longer in the tree, so it was either moved or removed
                    # Have we seen this hash before as a potentially-added record?
                    if record1.hash in potentially_added:
                        added_diff = potentially_added[record1.hash]
                        del potentially_added[record1.hash]

                        local_diff = MovedToDiff(record1, parent_diff, [], None)
                        moved_from_diff = MovedFromDiff(added_diff.record, added_diff.parent, [], local_diff)
                        local_diff.moved_to = moved_from_diff

                        # Replace the original added diff with a moved-from diff
                        added_diff.parent.children = (
                            [_ if _.record.hash != record1.hash
                             else moved_from_diff
                             for _ in added_diff.parent.children])

                    else:
                        local_diff = RemovedDiff(record1, parent_diff, [])
                        potentially_removed[record1.hash] = local_diff

                    parent_diff.children.append(local_diff)
                else:
                    record2 = records2[name]

                    # This record is identical in both trees, so no diff is needed
                    if record1.hash == record2.hash:
                        continue

                    # If the record is a tree, we need to recursively compare the trees
                    if record1.type == TreeRecordType.TREE and record2.type == TreeRecordType.TREE:
                        subtree_diff = ModifiedDiff(record1, parent_diff, [])

                        try:
                            tree1 = load_tree(self.objects_dir(), record1.hash)
                            tree2 = load_tree(self.objects_dir(), record2.hash)
                        except Exception as e:
                            msg = 'Error loading subtree for diff'
                            raise RepositoryError(msg) from e

                        stack.append((tree1, tree2, subtree_diff))
                        parent_diff.children.append(subtree_diff)
                    else:
                        modified_diff = ModifiedDiff(record1, parent_diff, [])
                        parent_diff.children.append(modified_diff)

            for name, record2 in records2.items():
                if name not in records1:
                    # This name is in the new tree but not in the old tree, so it was either
                    # added or moved
                    # If we've already seen this hash, it was moved, so convert the original
                    # added diff to a moved diff
                    if record2.hash in potentially_removed:
                        removed_diff = potentially_removed[record2.hash]
                        del potentially_removed[record2.hash]

                        local_diff = MovedFromDiff(record2, parent_diff, [], None)
                        moved_to_diff = MovedToDiff(removed_diff.record, removed_diff.parent, [], local_diff)
                        local_diff.moved_from = moved_to_diff

                        # Create a new diff for the moved record
                        removed_diff.parent.children = (
                            [_ if _.record.hash != record2.hash
                             else moved_to_diff
                             for _ in removed_diff.parent.children])

                    else:
                        local_diff = AddedDiff(record2, parent_diff, [])
                        potentially_added[record2.hash] = local_diff

                    parent_diff.children.append(local_diff)

        return top_level_diff.children

    def _collect_tree_blob_map(self, initial_tree_hash: str, initial_base_path: Path = Path()) -> dict[Path, HashRef]:
        """Collect a map of all blob paths and hashes reachable from a tree object iteratively."""
        blob_map: dict[Path, HashRef] = {}
        
        stack = [(initial_tree_hash, initial_base_path)]

        while stack:
            current_tree_hash, current_base_path = stack.pop()
            tree = load_tree(self.objects_dir(), current_tree_hash)

            for record in tree.records.values():
                record_path = current_base_path / record.name
                
                if record.type == TreeRecordType.BLOB:
                    blob_map[record_path] = HashRef(record.hash)
                elif record.type == TreeRecordType.TREE:
                    stack.append((record.hash, record_path))

        return blob_map
    
    def _collect_blob_map(self, commit_hash: HashRef | None) -> dict[Path, HashRef]:
        """Collect all tracked blob paths for a commit hash."""
        if commit_hash is None:
            return {}

        commit = load_commit(self.objects_dir(), commit_hash)
        return self._collect_tree_blob_map(commit.tree_hash)

    def _expand_tree_blob_paths(self, tree_hash: str, base_path: Path) -> set[Path]:
        """Expand a tree hash to all descendant blob paths under base_path."""
        return set(self._collect_tree_blob_map(tree_hash, base_path).keys())

    def _cleanup_empty_parents(self, start_path: Path) -> None:
        """Remove empty parent directories up to, but not including, the working directory."""
        current = start_path

        while current != self.working_dir and current != self.working_dir.parent:
            if not current.exists() or not current.is_dir():
                current = current.parent
                continue

            try:
                current.rmdir()
            except OSError:
                break

            current = current.parent

    def _assert_clean_workspace(self, current_blob_map: dict[Path, HashRef],
                                target_blob_map: dict[Path, HashRef],
                                added_paths: set[Path]) -> None:
        """Validate tracked files are clean and no incoming added file overwrites untracked data."""
        for path, current_hash in current_blob_map.items():
            target_hash = target_blob_map.get(path)
            if target_hash == current_hash:
                continue

            abs_path = self.working_dir / path

            if target_hash is None and not abs_path.exists():
                continue

            if not abs_path.exists() or not abs_path.is_file():
                raise RepositoryError(f'Checkout aborted: tracked path changed on disk: {path}')

            disk_hash = hash_file(abs_path)
            if disk_hash != current_hash:
                raise RepositoryError(f'Checkout aborted: dirty tracked file: {path}')

        for path in added_paths:
            for parent in path.parents:
                if parent in current_blob_map:
                    continue 
        
                abs_parent = self.working_dir / parent
                if abs_parent.exists() and not abs_parent.is_dir():
                    raise RepositoryError(f'Checkout aborted: untracked file blocks directory creation: {parent}')

            if path in current_blob_map:
                continue

            abs_path = self.working_dir / path
            if abs_path.exists():
                raise RepositoryError(f'Checkout aborted: untracked path in the way: {path}')

    def _apply_pass1_deletions(self, flattened_diffs: Sequence[tuple[Diff, Path]]) -> None:
        """Apply deletion pass: remove files/directories for RemovedDiff nodes."""
        deletion_items = [
            (diff, path)
            for diff, path in flattened_diffs
            if isinstance(diff, RemovedDiff)
        ]

        # Sort by path length descending to delete deepest items first
        deletion_items.sort(key=lambda item: len(item[1].parts), reverse=True)

        for diff, rel_path in deletion_items:
            abs_path = self.working_dir / rel_path
            if not abs_path.exists():
                continue

            if diff.record.type == TreeRecordType.TREE and abs_path.is_dir():
                for blob_path in self._expand_tree_blob_paths(diff.record.hash, rel_path):
                    tracked_file = self.working_dir / blob_path
                    if tracked_file.exists() and tracked_file.is_file():
                        tracked_file.unlink()
                        self._cleanup_empty_parents(tracked_file.parent)
                
                try:
                    abs_path.rmdir()
                except OSError:
                    pass
                continue

            if abs_path.is_file() or abs_path.is_symlink():
                abs_path.unlink()
                self._cleanup_empty_parents(abs_path.parent)

    def _apply_pass2_renames(self, move_pairs: Sequence[tuple[Path, Path]]) -> None:
        """Apply rename pass using a safe 2-phase temp shuffle to prevent chained move data loss."""
        if not move_pairs:
            return

        safe_moves: list[tuple[Path, Path, Path]] = []
        
        
        caf_dir = self.objects_dir().parent

        with tempfile.TemporaryDirectory(dir=caf_dir, prefix='tmp_renames_') as tmp_dir_name:
            tmp_dir = Path(tmp_dir_name)

            for src_rel, dst_rel in move_pairs:
                src_abs = self.working_dir / src_rel
                if not src_abs.exists():
                    continue

                tmp_path = tmp_dir / uuid.uuid4().hex
                os.rename(src_abs, tmp_path)
                
                safe_moves.append((tmp_path, dst_rel, src_abs.parent))

            for tmp_path, dst_rel, original_parent in safe_moves:
                dst_abs = self.working_dir / dst_rel
                os.makedirs(dst_abs.parent, exist_ok=True)

                if dst_abs.exists():
                    if dst_abs.is_dir():
                        shutil.rmtree(dst_abs)
                    else:
                        dst_abs.unlink()

                os.rename(tmp_path, dst_abs)
                self._cleanup_empty_parents(original_parent)

    def _apply_pass3_writes(self, flattened_diffs: Sequence[tuple[Diff, Path]],
                            target_blob_map: dict[Path, HashRef]) -> None:
        """Apply write pass for additions and modifications by restoring blobs and trees from the object database."""
        for diff, rel_path in flattened_diffs:
            abs_path = self.working_dir / rel_path
            if isinstance(diff, AddedDiff):
                if diff.record.type == TreeRecordType.TREE:
                    extract_tree_to_disk(self.objects_dir(), diff.record.hash, abs_path)
                else:
                    blob_hash = target_blob_map.get(rel_path)
                    if blob_hash is None:
                        continue

                    if abs_path.exists() and abs_path.is_dir():
                        shutil.rmtree(abs_path)

                    restore_blob_to_path(self.objects_dir(), blob_hash, abs_path)

            elif isinstance(diff, ModifiedDiff) and diff.record.type == TreeRecordType.BLOB:
                blob_hash = target_blob_map.get(rel_path)
                if blob_hash is None:
                    continue

                if abs_path.exists():
                    if abs_path.is_dir():
                        shutil.rmtree(abs_path)
                    else:
                        abs_path.unlink()

                restore_blob_to_path(self.objects_dir(), blob_hash, abs_path)
    
    @requires_repo
    def sync_working_dir_to_commit(self, target_hash: str) -> None:
        """Safely updates the physical files on disk to match a target commit."""
        current_hash = self.head_commit()
        if current_hash == target_hash:
            return

        current_blob_map = self._collect_blob_map(current_hash)
        target_blob_map = self._collect_blob_map(target_hash)

        diffs = self.diff_commits(current_hash, target_hash)
        flattened_diffs = flatten_diffs_with_paths(diffs)
        move_pairs = pair_moves(flattened_diffs)
        
        added_paths: set[Path] = {dst for _, dst in move_pairs}
        for diff, rel_path in flattened_diffs:
            if not isinstance(diff, AddedDiff):
                continue
            if diff.record.type == TreeRecordType.BLOB:
                added_paths.add(rel_path)
            elif diff.record.type == TreeRecordType.TREE:
                added_paths.update(self._expand_tree_blob_paths(diff.record.hash, rel_path))

        self._assert_clean_workspace(current_blob_map, target_blob_map, added_paths)
        self._apply_pass1_deletions(flattened_diffs)
        self._apply_pass2_renames(move_pairs)
        self._apply_pass3_writes(flattened_diffs, target_blob_map)

    @requires_repo
    def checkout(self, target_ref: Ref | str) -> None:
        """Checkout a target reference into the working directory and update HEAD."""
        
        # Normalize the incoming reference
        safe_ref = coerce_to_ref(target_ref)

        is_branch = False
        full_branch_ref = None

        # Check if the target is an existing branch
        if isinstance(safe_ref, SymRef):
            short_name = safe_ref.branch_name()
            if self.branch_exists(SymRef(short_name)):
                is_branch = True
                full_branch_ref = SymRef(f"heads/{short_name}")
                safe_ref = full_branch_ref

        target_hash = self.resolve_ref(safe_ref)
        
        if target_hash is None:
            raise RefError(f"Cannot resolve reference: '{target_ref}'")

        self.sync_working_dir_to_commit(target_hash)
        
        # Update HEAD (Attach vs. Detach)
        if is_branch and full_branch_ref:
            # It's a branch: Attach HEAD
            self.update_head(full_branch_ref)
        else:
            # It's a tag or a raw commit hash: Detach HEAD
            self.update_head(HashRef(target_hash))
    
    @requires_repo
    def tags_dir(self) -> Path:
        """Get the path to the tags directory within the repository.

        :return: The path to the tags directory."""
        return self.refs_dir() / TAGS_DIR
    
    @requires_repo
    def tag_exists(self, tag_name: str) -> bool:
        """Check if a tag exists in the repository.

        :param tag_name: The name of the tag to check.
        :return: True if the tag exists, False otherwise."""
        return (self.tags_dir() / tag_name).exists()

    @requires_repo
    def create_tag(self, tag_name: str, commit_ref: Ref) -> None:
        """Create a new tag in the repository.

        :param tag_name: The name of the tag to create.
        :param commit_ref: The reference to the commit the tag points to.
        :raises ValueError: If parameters are empty.
        :raises RepositoryError: If the tag already exists or if the repository doesn't exist."""
        if not tag_name:            
            raise ValueError("Tag name is missing")
        if not commit_ref:
            raise ValueError("Commit reference is missing")
        if self.tag_exists(tag_name):
            raise RepositoryError(f'Tag "{tag_name}" already exists')
        # Ensure the tags directory exists
        self.tags_dir().mkdir(parents=True, exist_ok=True)
        try:
            commit_hash = self.resolve_ref(commit_ref)
            if not commit_hash:
                raise RepositoryError(f'Commit {commit_ref} cannot be resolved')
            load_commit(self.objects_dir(), commit_hash)            
            write_ref(self.tags_dir() / tag_name, commit_hash)
        except RefError as e:
             raise RepositoryError(f'Invalid commit reference: {e}')
        except Exception:
             raise RepositoryError(f'Commit "{commit_ref}" does not exist')
        
    @requires_repo
    def delete_tag(self, tag_name: str) -> None:
        """Delete a tag from the repository.

        :param tag_name: The name of the tag to delete.
        :raises ValueError: If tag_name is empty.
        :raises RepositoryError: If the tag does not exist."""
        if not tag_name:
            raise ValueError('Tag name is missing')

        if not self.tag_exists(tag_name):
            raise RepositoryError(f'Tag "{tag_name}" does not exist')

        (self.tags_dir() / tag_name).unlink()

    @requires_repo
    def tags(self) -> list[str]:
        """Get a list of all tags in the repository.

        :return: A list of tag names, sorted alphabetically."""
        if not self.tags_dir().exists():
            return []
        
        return sorted([x.name for x in self.tags_dir().iterdir() if x.is_file()])

    @requires_repo
    def head_file(self) -> Path:
        """Get the path to the HEAD file within the repository.
                
        :return: The path to the HEAD file."""
        return self.repo_path() / HEAD_FILE
    
    @requires_repo
    def merge_head_file(self) -> Path:
        """Get the path to the MERGE_HEAD file within the repository.
                
        :return: The path to the MERGE_HEAD file."""
        return self.repo_path() / MERGE_HEAD_FILE
    

    def update_head(self, target_ref: Ref) -> None:
        """
        Update the HEAD file to point to a specific reference.
        
        If a symbolic reference (like a branch name) is provided, HEAD attaches to the branch.
        If a direct commit hash is provided, it results in a 'detached HEAD' state.

        :param target_ref: The Ref (SymRef or HashRef) to write into HEAD.
        :raises RepositoryNotFoundError: If the repository is not initialized.
        """
        write_ref(self.head_file(), target_ref)

    @requires_repo
    def merge(self, target_ref: Ref, source_ref: Ref, author: str) -> MergeReport:
        """
        Merges the source_branch into target_branch.
        """
        target_hash = self.resolve_ref(target_ref)
        source_hash = self.resolve_ref(source_ref)

        if target_hash is None:
            raise RefError(f"Target reference {target_ref} cannot be resolved")
        if source_hash is None:
            raise RefError(f"Source reference {source_ref} cannot be resolved")
    
        try:
            target_commit = load_commit(self.objects_dir(), target_hash)
        except Exception:
            raise RepositoryError(f"Target commit {target_hash} not found or invalid")

        try:
            source_commit = load_commit(self.objects_dir(), source_hash)
        except Exception:
            raise RepositoryError(f"Source commit {source_hash} not found or invalid")

        lca = find_lca(self.objects_dir(), target_hash, source_hash)


        if lca is None:
            raise NotImplementedError("Unrelated histories is not supported")

        if lca == source_hash:
            return MergeReport(MergeResult.UP_TO_DATE, target_hash)

        if lca == target_hash:
            return MergeReport(MergeResult.FAST_FORWARD, source_hash)
        
        # Perform a three-way merge using the LCA commit as the common ancestor
        if not author:
            raise RepositoryError("Author name is required to auto-create a merge commit.")

        lca_commit = load_commit(self.objects_dir(), lca)
        merge_plan = merge_trees(lca_commit.tree_hash, target_commit.tree_hash, source_commit.tree_hash,
                                 lambda h: load_tree(self.objects_dir(), h))
        root_hash, conflicts, clean_updates, deletions = compute_merge_tree(self.objects_dir(), merge_plan)
        if conflicts:
            return MergeReport(MergeResult.CONFLICTS, target_hash, clean_updates, deletions, conflicts)
        
        new_commit = Commit(root_hash, author, f'Merge {source_ref} into {target_ref}', int(datetime.now().timestamp()), [target_hash, source_hash])
        save_commit(self.objects_dir(), new_commit)
        new_commit_hash = hash_object(new_commit)
        return MergeReport(MergeResult.MERGE_CREATED, new_commit_hash, clean_updates, deletions, conflicts)

    @requires_repo
    def apply_conflicts_to_disk(self, conflicts: list[Tuple[str, MergeConflict]], source_hash: str) -> None:
        """
        Apply conflict markers to the working directory for a list of conflicts.
        This is used to write the conflict state to disk after a merge with conflicts.

        :param conflicts: A list of tuples containing the file path and MergeConflict details.
        :param source_hash: The hash of the source commit involved in the merge conflict.
        """
        if not conflicts:
            return
        objects_dir = self.objects_dir()
        for path_str, conflict in conflicts:
            abs_path = self.working_dir / path_str
            abs_path.parent.mkdir(parents=True, exist_ok=True)
            if conflict.conflict_type == "content":
                if not is_binary_blob(objects_dir / conflict.ours_hash[:2] / conflict.ours_hash) and not is_binary_blob(objects_dir / conflict.theirs_hash[:2] / conflict.theirs_hash):
                    with ExitStack() as file_stack:
                        base_seq = file_stack.enter_context(prepare_lines_sequence(objects_dir / conflict.base_hash[:2] / conflict.base_hash)) if conflict.base_hash else []
                        ours_seq = file_stack.enter_context(prepare_lines_sequence(objects_dir / conflict.ours_hash[:2] / conflict.ours_hash))
                        theirs_seq = file_stack.enter_context(prepare_lines_sequence(objects_dir / conflict.theirs_hash[:2] / conflict.theirs_hash))
                        three_way_merge(base_seq, ours_seq, theirs_seq, abs_path)
                else: 
                    # Binary conflict: # our version is already on disk. Extract theirs as a sidecar for comparison.
                    conflict_dest = self.working_dir / f"{path_str}~MERGE_HEAD"
                    restore_blob_to_path(objects_dir, conflict.theirs_hash, conflict_dest)

            elif conflict.conflict_type == "modify/delete":
                if not conflict.ours_hash and conflict.theirs_hash:
                    restore_blob_to_path(objects_dir, conflict.theirs_hash, abs_path)

            elif conflict.conflict_type == "type":
                if conflict.ours_hash and conflict.ours_type == TreeRecordType.BLOB:
                    conflict_dest = self.working_dir / f"{path_str}~HEAD"
                    if abs_path.exists() and abs_path.is_file():
                        abs_path.rename(conflict_dest)
                    else:
                        restore_blob_to_path(objects_dir, conflict.ours_hash, conflict_dest)
                        
                    if conflict.theirs_hash and conflict.theirs_type == TreeRecordType.TREE:
                        extract_tree_to_disk(objects_dir, conflict.theirs_hash, abs_path)

                if conflict.theirs_hash and conflict.theirs_type == TreeRecordType.BLOB:
                    conflict_dest = self.working_dir / f"{path_str}~MERGE_HEAD"
                    restore_blob_to_path(objects_dir, conflict.theirs_hash, conflict_dest)
                
        write_ref(self.merge_head_file(), HashRef(source_hash))
    
    @requires_repo
    def apply_clean_updates_to_disk(self, merge_report: 'MergeReport') -> None:
        """Apply all non-conflicting additions, updates, and deletions to the workspace."""
        
        # Apply all cleanly added, updated, or auto-merged files and directories
        for path_str, record in merge_report.clean_updates.items():
            abs_path = self.working_dir / path_str
            
            if record.type == TreeRecordType.TREE:
                extract_tree_to_disk(self.objects_dir(), record.hash, abs_path)
            else:
                abs_path.parent.mkdir(parents=True, exist_ok=True)
                restore_blob_to_path(str(self.objects_dir()), record.hash, str(abs_path))
                
        # Physically remove files that were cleanly deleted by the merge
        for path_str in merge_report.deletions:
            file_path = self.working_dir / path_str
            if file_path.exists():
                file_path.unlink()
                
            try:
                file_path.parent.rmdir()
            except OSError:
                pass # Directory not empty, ignore
    
    @requires_repo
    def abort_merge(self) -> None:
        """Abort an in-progress merge, safely restoring HEAD."""
        
        merge_head_file = self.merge_head_file()
        if not merge_head_file.exists():
            raise RepositoryError('No merge in progress to abort.')

        head_hash = self.head_commit()
        if not head_hash:
            raise RepositoryError('Cannot abort merge: HEAD commit not found.')

        head_blob_map = self._collect_blob_map(head_hash)
        try:
            raw_hash = merge_head_file.read_text().strip()
            merge_head_hash = HashRef(raw_hash) if raw_hash else None
            merge_blob_map = self._collect_blob_map(merge_head_hash) if merge_head_hash else {}
        except RuntimeError:
            merge_blob_map = {}

        commit = load_commit(self.objects_dir(), head_hash)
        extract_tree_to_disk(self.objects_dir(), commit.tree_hash, self.working_dir)

        # Safe Cleanup Sweep (Sidecars and Ghost Files)
        for file_path in self.working_dir.rglob('*'):
            if self.repo_dir.name in file_path.parts or not file_path.is_file():
                continue
                
            # Sweep structural conflict backup sidecars
            if file_path.name.endswith('~HEAD') or file_path.name.endswith('~MERGE_HEAD'):
                file_path.unlink()
                continue 

            # Sweep Ghost Files
            rel_path = file_path.relative_to(self.working_dir)
            in_head = (rel_path in head_blob_map) or (str(rel_path) in head_blob_map)
            in_merge = (rel_path in merge_blob_map) or (str(rel_path) in merge_blob_map)

            if not in_head and in_merge:
                file_path.unlink()

        # Bottom-Up Empty Directory Prune
        repo_dirs = [d for d in self.working_dir.rglob('*') 
                    if d.is_dir() and self.repo_dir.name not in d.parts]
        repo_dirs.sort(key=lambda p: len(p.parts), reverse=True)
        
        for d in repo_dirs:
            if not any(d.iterdir()):
                d.rmdir()

        # Unlock the repo by completing the abort
        merge_head_file.unlink()


def branch_ref(branch: str) -> SymRef:
    """Create a symbolic reference for a branch name.

    :param branch: The name of the branch.
    :return: A SymRef object representing the branch reference."""
    return SymRef(f'{HEADS_DIR}/{branch}')


def flatten_diffs_with_paths(initial_diffs: Sequence[Diff], initial_parent_path: Path = Path()) -> list[tuple[Diff, Path]]:
    """Flatten nested diffs into a list with their working-tree relative paths iteratively."""
    flattened: list[tuple[Diff, Path]] = []
    
    # The stack stores tuples of: (list_of_diffs, their_parent_path)
    stack = [(initial_diffs, initial_parent_path)]

    while stack:
        current_diffs, current_parent = stack.pop()
        
        for diff in current_diffs:
            # Calculate the path for the current diff
            current_path = current_parent / diff.record.name if diff.record.name else current_parent
            flattened.append((diff, current_path))
            
            if diff.children:
                stack.append((diff.children, current_path))

    return flattened


def pair_moves(flattened_diffs: Sequence[tuple[Diff, Path]]) -> list[tuple[Path, Path]]:
    """Extract source/destination path pairs for moved records."""
    path_by_diff_id = {id(diff): path for diff, path in flattened_diffs}
    
    move_pairs_dict: dict[tuple[Path, Path], None] = {}

    for diff, dst_path in flattened_diffs:
        if not isinstance(diff, MovedFromDiff) or diff.moved_from is None:
            continue

        src_path = path_by_diff_id.get(id(diff.moved_from))
        if src_path is None:
            continue

        pair = (src_path, dst_path)
        move_pairs_dict[pair] = None 

    return list(move_pairs_dict.keys())


def extract_tree_to_disk(objects_dir: Path, tree_hash: str, dest_dir: Path) -> None:
    """Extracts a Tree object from the database to the physical disk iteratively."""
    dest_dir.mkdir(parents=True, exist_ok=True)

    stack = [(tree_hash, dest_dir)]
    
    while stack:
        current_tree_hash, current_dest_dir = stack.pop()
        tree = load_tree(objects_dir, current_tree_hash)
        
        for name, record in tree.records.items():
            child_path = current_dest_dir / name
            
            if record.type == TreeRecordType.BLOB:
                restore_blob_to_path(objects_dir, record.hash, child_path)
                
            elif record.type == TreeRecordType.TREE:
                child_path.mkdir(parents=True, exist_ok=True)
                stack.append((record.hash, child_path))