"""CLI command implementations for CAF (Content Addressable File system)."""

import sys
from collections.abc import MutableSequence, Sequence
from datetime import datetime
from pathlib import Path

from libcaf.constants import DEFAULT_BRANCH, HASH_LENGTH
from libcaf.plumbing import hash_file as plumbing_hash_file
from libcaf.ref import SymRef, HashRef, RefError
from libcaf.repository import (AddedDiff, Diff, ModifiedDiff, MovedToDiff, RemovedDiff, Repository, RepositoryError,
                               RepositoryNotFoundError, MergeResult)


def _print_error(message: str) -> None:
    print(f'❌ Error: {message}', file=sys.stderr)


def _print_success(message: str) -> None:
    print(message)


def init(**kwargs) -> int:
    repo = _repo_from_cli_kwargs(kwargs)
    default_branch = kwargs.get('default_branch', DEFAULT_BRANCH)

    try:
        repo.init(default_branch)
        _print_success(f'Initialized empty CAF repository in {repo.repo_path()} on branch {default_branch}')
        return 0
    except FileExistsError:
        _print_error(f'CAF repository already exists in {repo.working_dir}')
        return -1


def delete_repo(**kwargs) -> int:
    repo = _repo_from_cli_kwargs(kwargs)

    try:
        repo.delete_repo()
        _print_success(f'Deleted repository at {repo.repo_path()}')
        return 0
    except RepositoryNotFoundError:
        _print_error(f'No repository found at {repo.repo_path()}')
        return -1


def hash_file(**kwargs) -> int:
    path = Path(kwargs['path'])

    if not path.exists():
        _print_error(f'File {path} does not exist.')
        return -1

    file_hash = plumbing_hash_file(path)
    _print_success(f'Hash: {file_hash}')

    if not kwargs.get('write', False):
        return 0

    repo = _repo_from_cli_kwargs(kwargs)

    try:
        repo.save_file_content(path)
        _print_success(f'Saved file {path} to CAF repository')
        return 0
    except RepositoryNotFoundError:
        _print_error(f'No repository found at {repo.repo_path()}')
        return -1

def create_tag(**kwargs) -> int:
    repo = _repo_from_cli_kwargs(kwargs)
    tag_name = kwargs.get('tag_name')
    commit_hash = kwargs.get('commit_hash')

    if not tag_name:
        _print_error('Tag name is required.')
        return -1
    if not commit_hash:
        _print_error('Commit hash is required.')
        return -1

    try:
        repo.create_tag(tag_name, commit_hash)
        _print_success(f'Tag "{tag_name}" created for commit {commit_hash}.')
        return 0
    except RepositoryNotFoundError:
        _print_error(f'No repository found at {repo.repo_path()}')
        return -1
    except RepositoryError as e:
        _print_error(f'Repository error: {e}')
        return -1
    

def delete_tag(**kwargs) -> int:
    repo = _repo_from_cli_kwargs(kwargs)
    tag_name = kwargs.get('tag_name')

    if not tag_name:
        _print_error('Tag name is required.')
        return -1

    try:
        repo.delete_tag(tag_name)
        _print_success(f'Tag "{tag_name}" deleted.')
        return 0
    except RepositoryNotFoundError:
        _print_error(f'No repository found at {repo.repo_path()}')
        return -1
    except RepositoryError as e:
        _print_error(f'Repository error: {e}')
        return -1
    
def tags(**kwargs) -> int:
    repo = _repo_from_cli_kwargs(kwargs)
    
    try:
        tag_list = repo.tags()

        if not tag_list:
            _print_success('No tags found.')
            return 0

        _print_success('Tags:')
        for tag in tag_list:
            print(f'  {tag}')
        
        return 0
    except RepositoryNotFoundError:
        _print_error(f'No repository found at {repo.repo_path()}')
        return -1
    except RepositoryError as e:
        _print_error(f'Repository error: {e}')
        return -1

def add_branch(**kwargs) -> int:
    repo = _repo_from_cli_kwargs(kwargs)
    branch_name = kwargs.get('branch_name')

    if not branch_name:
        _print_error('Branch name is required.')
        return -1

    try:
        repo.add_branch(branch_name)
        _print_success(f'Branch "{branch_name}" created.')
        return 0
    except RepositoryNotFoundError:
        _print_error(f'No repository found at {repo.repo_path()}')
        return -1
    except RepositoryError as e:
        _print_error(f'Repository error: {e}')
        return -1


def delete_branch(**kwargs) -> int:
    repo = _repo_from_cli_kwargs(kwargs)
    branch_name = kwargs.get('branch_name')

    if not branch_name:
        _print_error('Branch name is required.')
        return -1

    try:
        repo.delete_branch(branch_name)
        _print_success(f'Branch "{branch_name}" deleted.')
        return 0
    except RepositoryNotFoundError:
        _print_error(f'No repository found at {repo.repo_path()}')
        return -1
    except RepositoryError as e:
        _print_error(f'Repository error: {e}')
        return -1


def branch_exists(**kwargs) -> int:
    repo = _repo_from_cli_kwargs(kwargs)
    branch_name = kwargs.get('branch_name')

    if not branch_name:
        _print_error('Branch name is required.')
        return -1

    try:
        if repo.branch_exists(SymRef(branch_name)):
            _print_success(f'Branch "{branch_name}" exists.')
            return 0

        _print_error(f'Branch "{branch_name}" does not exist.')
        return -1
    except RepositoryNotFoundError:
        _print_error(f'No repository found at {repo.repo_path()}')
        return -1


def branch(**kwargs) -> int:
    repo = _repo_from_cli_kwargs(kwargs)
    try:
        branches = repo.branches()

        if not branches:
            _print_success('No branches found.')
            return 0

        _print_success('Branches:')

        current_head = repo.head_ref()

        # Extract branch name from SymRef if HEAD points to a branch
        current_branch = current_head.branch_name() if isinstance(current_head, SymRef) else None

        for branch in branches:
            if branch == current_branch:
                print(f'* {branch}')
            else:
                print(branch)
    except RepositoryNotFoundError:
        _print_error(f'No repository found at {repo.repo_path()}')
        return -1
    except RepositoryError as e:
        _print_error(f'Repository error: {e}')
        return -1

    return 0


def commit(**kwargs) -> int:
    repo = _repo_from_cli_kwargs(kwargs)
    author = kwargs.get('author')
    message = kwargs.get('message')

    if not author:
        _print_error('Author name is required.')
        return -1
    if not message:
        _print_error('Commit message is required.')
        return -1

    try:
        commit_ref = repo.commit_working_dir(author, message)

        _print_success(f'Commit created successfully:\n'
                       f'Hash: {commit_ref}\n'
                       f'Author: {author}\n'
                       f'Message: {message}\n')
        return 0
    except RepositoryNotFoundError:
        _print_error(f'No repository found at {repo.repo_path()}')
        return -1
    except RepositoryError as e:
        _print_error(f'Repository error: {e}')
        return -1


def log(**kwargs) -> int:
    repo = _repo_from_cli_kwargs(kwargs)

    try:
        history = list(repo.log())
        if not history:
            _print_success('No commits in the repository.')
            return 0

        _print_success('Commit history:\n')
        for item in history:
            commit = item.commit

            print(f'Commit: {item.commit_ref}')
            print(f'Author: {commit.author}')
            commit_date = datetime.fromtimestamp(commit.timestamp).strftime('%Y-%m-%d %H:%M:%S')
            print(f'Date: {commit_date}\n')
            for line in commit.message.splitlines():
                print(f'    {line}')
            print('\n' + '-' * 50 + '\n')

        return 0
    except RepositoryNotFoundError:
        _print_error(f'No repository found at {repo.repo_path()}')
        return -1
    except RepositoryError as re:
        _print_error(f'Repository error: {re}')
        return -1


def diff(**kwargs) -> int:
    repo = _repo_from_cli_kwargs(kwargs)
    commit1 = kwargs.get('commit1')
    commit2 = kwargs.get('commit2')

    if not commit1 or not commit2:
        _print_error('Both commit1 and commit2 parameters are required for diff.')
        return -1

    try:
        diffs = repo.diff_commits(commit1, commit2)

        if not diffs:
            _print_success('No changes detected between commits.')
            return 0

        _print_diffs([(diffs, 0)])

        return 0
    except RepositoryNotFoundError:
        _print_error(f'No repository found at {repo.repo_path()}')
        return -1
    except RepositoryError as e:
        _print_error(f'Repository error: {e}')
        return -1


def _repo_from_cli_kwargs(kwargs: dict[str, str]) -> Repository:
    working_dir_path = kwargs.get('working_dir_path', '.')
    repo_dir = kwargs.get('repo_dir')

    return Repository(working_dir_path, repo_dir)


def _print_diffs(diff_stack: MutableSequence[tuple[Sequence[Diff], int]]) -> None:
    _print_success('Diff:\n')

    while diff_stack:
        current_diffs, indent = diff_stack.pop()
        for diff in current_diffs:
            print(' ' * indent, end='')

            match diff:
                case AddedDiff(record, _, _):
                    print(f'Added: {record.name}')
                case ModifiedDiff(record, _, _):
                    print(f'Modified: {record.name}')
                case MovedToDiff(record, _, _, moved_to):
                    assert moved_to is not None, 'MovedToDiff must have a moved_to record, this is a bug!'
                    print(f'Moved: {record.name} -> {moved_to.record.name}')
                case RemovedDiff(record, _, _):
                    print(f'Removed: {record.name}')
                case _:
                    pass

            if diff.children:
                diff_stack.append((diff.children, indent + 3))


def merge(**kwargs) -> int:
    repo = _repo_from_cli_kwargs(kwargs)
    if kwargs.get('abort'):
        try:
            repo.abort_merge() 
            _print_success("✅ Merge aborted successfully. Workspace restored.")
            return 0
        except RepositoryError as e:
            _print_error(f"Failed to abort merge: {e}")
            return -1

    raw_target = kwargs.get('target_ref')
    author = kwargs.get('author') or ""
    
    if not raw_target:
        _print_error('Target reference is required for merge.')
        return -1
        
    try:
        is_hash = len(raw_target) == HASH_LENGTH and all(c in '0123456789abcdef' for c in raw_target.lower())
        
        target_ref = None
        target_hash = None

        if is_hash:
            target_ref = HashRef(raw_target)
            try:
                target_hash = repo.resolve_ref(target_ref)
            except (RefError, OSError): 
                pass # Handled below if it fails
        else:
            if raw_target.startswith('heads/') or raw_target.startswith('tags/'):
                candidates = [raw_target]
            else:
                # Ambiguous input! Try branch first, then fallback to tag
                candidates = [f'heads/{raw_target}', f'tags/{raw_target}']
            
            for candidate in candidates:
                try:
                    temp_ref = SymRef(candidate)
                    possible_hash = repo.resolve_ref(temp_ref)
                    if possible_hash:
                        target_ref = temp_ref
                        target_hash = possible_hash
                        break 
                except (RefError, OSError):
                    # Ignore the FileNotFoundError and try the next candidate in the list
                    continue

        if not target_hash or not target_ref:
            _print_error(f'Could not resolve branch, tag, or commit reference: {raw_target}')
            return -1

        current_head = repo.head_ref()
        merge_report = repo.merge(current_head, target_ref, author)
        
        match merge_report.status:
            case MergeResult.FAST_FORWARD:
                repo.sync_working_dir_to_commit(target_hash)
                if isinstance(current_head, SymRef):
                    repo.update_ref(current_head, target_hash)
                else:
                    # Detached HEAD fix: advance the HEAD pointer directly
                    repo.update_head(HashRef(target_hash))
                _print_success(f'Merge completed with a fast-forward. Current branch now points to {target_ref}.')
                return 0            
                
            case MergeResult.UP_TO_DATE:
                _print_success(f'Current branch is already up to date with {target_ref}. No merge needed.')
                return 0
                
            case MergeResult.MERGE_CREATED:
                repo.sync_working_dir_to_commit(merge_report.commit_hash)
                if isinstance(current_head, SymRef):
                    repo.update_ref(current_head, merge_report.commit_hash)
                else:
                    # Detached HEAD fix: advance the HEAD pointer directly
                    repo.update_head(HashRef(merge_report.commit_hash))
                _print_success(f'Merge completed with a new merge commit. Current branch now points to {merge_report.commit_hash}.')
                return 0
                
            case MergeResult.CONFLICTS:
                repo.apply_clean_updates_to_disk(merge_report)
                repo.apply_conflicts_to_disk(merge_report.conflicts, target_hash)
                
                _print_success(f'\n⚠️  Merge conflict detected when merging {target_ref}.')
                _print_success('Automatic merge failed. Unresolved conflicts in:')
                
                for path_str, _ in merge_report.conflicts:
                    _print_success(f'  - {path_str}')
                    
                _print_success('\nPlease resolve the text markers, delete any backup files (~HEAD), and run "caf commit".')
                return -1
                
    except RepositoryNotFoundError:
        _print_error(f'No repository found at {repo.repo_path()}')
        return -1
    except RepositoryError as e:    
        _print_error(f'Repository error: {e}')
        return -1
    except NotImplementedError as e:
        _print_error(f'Merge operation not implemented: {e}')
        return -1
    except Exception as e:  # noqa: BLE001
        _print_error(f'Unexpected error during merge: {e}')
        return -1