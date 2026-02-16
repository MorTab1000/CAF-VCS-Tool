from typing import Set, Optional
from collections import deque
from pathlib import Path
from libcaf.repository import Repository, load_commit, TreeRecordType, TreeRecord
from enum import Enum, auto
from dataclasses import dataclass, field
from libcaf.plumbing import load_tree


def find_lca(repo_objects_dir: Path, hash_a: str, hash_b: str) -> Optional[str]:
    """
    Finds the Lowest Common Ancestor (LCA) of two commits.
    """
    if not hash_a or not hash_b:
        return None
    
    if hash_a == hash_b:
        return hash_a

    # 1. Collect all ancestors of A
    ancestors_a: Set[str] = set()
    stack = [hash_a]
    
    while stack:
        current = stack.pop()
        if current in ancestors_a:
            continue
        
        ancestors_a.add(current)
        commit = load_commit(repo_objects_dir, current)
        stack.extend(commit.parents)

    # 2. Walk up B's history and look for the first match in A's set
    # Using a BFS here ensures we find the "closest" ancestor first
    queue = deque([hash_b])
    visited_b: Set[str] = set()

    while queue:
        current = queue.popleft() # FIFO for BFS (closest first)
        
        if current in ancestors_a:
            return current
        
        if current in visited_b:
            continue
        visited_b.add(current)
        commit = load_commit(repo_objects_dir, current)
        parents = commit.parents
        queue.extend(parents) # Add from the right

    return None # No common ancestor found (orphan branches)


class MergeAction(Enum):
    TAKE_OURS = auto()         # Changed only in ours (or identical in both)
    TAKE_THEIRS = auto()       # Changed only in theirs
    MERGE_CONTENT = auto()     # File changed differently in both (Needs merge3 for text)
    MERGE_DIRECTORY = auto()   # Directory changed in both, need to recurse into its children
    CONFLICT = auto()          # Structural conflict (cannot be auto-merged)
    DELETE = auto()            # Deleted in one side and unchanged in the other, or deleted in both

class ConflictType(Enum):
    MODIFY_DELETE = auto()     # One side modified the file, the other side deleted it
    FILE_DIR = auto()          # One side made it a file, the other made it a directory
    
@dataclass
class MergeNode:
    name: str
    action: MergeAction
    record_type: Optional[TreeRecordType] = None
    base_hash: Optional[str] = None
    ours_hash: Optional[str] = None
    theirs_hash: Optional[str] = None
    conflict_type: Optional[ConflictType] = None
    children: list["MergeNode"] = field(default_factory=list)


def resolve_merge_tree(repo: Repository, base_tree_hash: str, ours_tree_hash: str, theirs_tree_hash: str) -> MergeNode:
    """
    Entry point to generate the intermediate Merge Tree for the 3-way merge.
    """
    # Create fake root records to kick off the recursion
    base_rec = TreeRecord(TreeRecordType.TREE, base_tree_hash, "") if base_tree_hash else None
    ours_rec = TreeRecord(TreeRecordType.TREE, ours_tree_hash, "")
    theirs_rec = TreeRecord(TreeRecordType.TREE, theirs_tree_hash, "")

    return _build_merge_node_recursive(repo, "", base_rec, ours_rec, theirs_rec)


def _build_merge_node_recursive(
    repo: Repository, 
    name: str,
    base_rec: Optional[TreeRecord],
    ours_rec: Optional[TreeRecord],
    theirs_rec: Optional[TreeRecord]
) -> MergeNode:
    """
    Recursively compares TreeRecords from Base, Ours, and Theirs, and decides the MergeAction.
    """
    b_hash = base_rec.hash if base_rec else None
    o_hash = ours_rec.hash if ours_rec else None
    t_hash = theirs_rec.hash if theirs_rec else None

    node = MergeNode(
        name=name, 
        action=MergeAction.CONFLICT, # Default, overridden below
        base_hash=b_hash, 
        ours_hash=o_hash, 
        theirs_hash=t_hash
    )

    # 1. Identical changes in both branches (or no change)
    if o_hash == t_hash:
        if o_hash is None:
            node.action = MergeAction.DELETE
        else:
            node.action = MergeAction.TAKE_OURS
            node.record_type = ours_rec.type
        return node

    # 2. Fast-forward cases (Only one side changed it)
    if o_hash == b_hash:  # We didn't touch it, but they did
        if t_hash is None:
            node.action = MergeAction.DELETE
        else:
            node.action = MergeAction.TAKE_THEIRS
            node.record_type = theirs_rec.type
        return node

    if t_hash == b_hash:  # They didn't touch it, but we did
        if o_hash is None:
            node.action = MergeAction.DELETE
        else:
            node.action = MergeAction.TAKE_OURS
            node.record_type = ours_rec.type
        return node

    # --- 3. True Divergence (Both changed it differently) ---

    # Case A: One side modified, the other deleted
    if o_hash is None or t_hash is None:
        node.action = MergeAction.CONFLICT
        node.conflict_type = ConflictType.MODIFY_DELETE
        return node

    # Case B: Type mismatch (e.g., File vs. Directory)
    if ours_rec.type != theirs_rec.type:
        node.action = MergeAction.CONFLICT
        node.conflict_type = ConflictType.FILE_DIR
        return node

    # Case C: Both are Files (Blobs) -> Needs content merge!
    node.record_type = ours_rec.type
    if ours_rec.type == TreeRecordType.BLOB:
        node.action = MergeAction.MERGE_CONTENT
        return node

    # Case D: Both are Directories (Trees) -> Recurse!
    if ours_rec.type == TreeRecordType.TREE:
        node.action = MergeAction.MERGE_DIRECTORY
        
        # Load the actual tree objects from the database
        tree_base = load_tree(repo.objects_dir(), b_hash) if b_hash else None
        tree_ours = load_tree(repo.objects_dir(), o_hash)
        tree_theirs = load_tree(repo.objects_dir(), t_hash)

        # Get dictionaries of child records
        base_children = tree_base.records if tree_base else {}
        ours_children = tree_ours.records if tree_ours else {}
        theirs_children = tree_theirs.records if tree_theirs else {}

        # Union of all unique child names from all three trees
        all_child_names = set(base_children.keys()) | set(ours_children.keys()) | set(theirs_children.keys())

        # Sort alphabetically to be deterministic
        for child_name in sorted(all_child_names):
            child_node = _build_merge_node_recursive(
                repo, 
                child_name,
                base_children.get(child_name),
                ours_children.get(child_name),
                theirs_children.get(child_name)
            )
            node.children.append(child_node)

        return node
    
    raise NotImplementedError(f"Unsupported tree record type: {ours_rec.type}")
