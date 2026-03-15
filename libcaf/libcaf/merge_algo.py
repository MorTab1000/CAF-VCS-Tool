from collections import deque
from pathlib import Path
from dataclasses import dataclass
from typing import Optional, Dict, Union, Tuple, Callable
from . import TreeRecordType, Tree, TreeRecord
from libcaf.plumbing import save_tree, load_commit, hash_object


def find_lca(repo_objects_dir: Path, hash_a: str, hash_b: str) -> Optional[str]:
    """
    Finds the Lowest Common Ancestor (LCA) of two commits.
    """
    if not hash_a or not hash_b:
        return None
    
    if hash_a == hash_b:
        return hash_a

    # 1. Collect all ancestors of A
    ancestors_a: set[str] = set()
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
    visited_b: set[str] = set()

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


@dataclass(frozen=True)
class MergeConflict:
    """An immutable record of a conflict to be resolved by the execution engine."""
    base_hash: Optional[str]
    ours_hash: Optional[str]
    theirs_hash: Optional[str]
    conflict_type: str  # "content", "modify/delete", or "type"

MergeResult = Dict[str, Union[TreeRecord, MergeConflict, dict]]


def merge_trees(base_hash: Optional[str], ours_hash: Optional[str], theirs_hash: Optional[str], fetch_tree: Callable[[str], Tree]) -> MergeResult:
    """
    Compares three trees and returns the NEW directory structure.
    Recursively handles sub-directories.
    """
    # 1. Load the three tree dictionaries (Path -> Hash)
    # (Helper function 'load_tree_dict' returns {} if hash is None)
    result = {}
    base_records = fetch_tree(base_hash).records if base_hash else {}
    ours_records = fetch_tree(ours_hash).records if ours_hash else {}
    theirs_records = fetch_tree(theirs_hash).records if theirs_hash else {}

    all_paths = sorted(set(base_records) | set(ours_records) | set(theirs_records))

    for path in all_paths:
        b_rec, o_rec, t_rec = base_records.get(path), ours_records.get(path), theirs_records.get(path)
        b_hash = b_rec.hash if b_rec else None
        o_hash, o_type = (o_rec.hash, o_rec.type) if o_rec else (None, None)
        t_hash, t_type = (t_rec.hash, t_rec.type) if t_rec else (None, None)         

         #case 1: fast forward or identical     
        if o_hash == t_hash:
            if o_hash:
                result[path] = o_rec
        
        elif b_hash == o_hash:
            if t_hash:
                result[path] = t_rec
        
        elif b_hash == t_hash:
            if o_hash:
                result[path] = o_rec

        #case 2: both dirs, need to recurse
        elif o_type == t_type == TreeRecordType.TREE:            
            result[path] = merge_trees(b_hash, o_hash, t_hash, fetch_tree)
       
        #case 3: content conflict
        else:
            # categorize the conflict type
            if o_hash is None or t_hash is None:
                conflict_type = "modify/delete"
            elif o_type != t_type:
                conflict_type = "type"
            else:
                conflict_type = "content"
            result[path] = MergeConflict(b_hash, o_hash, t_hash, conflict_type)

    return result
    

def execute_merge(repo_dir: Path, merge_result: MergeResult, current_path: str = "") -> Tuple[Optional[str], list[Tuple[str, MergeConflict]], dict[str, str]]:


    records = {}
    conflicts = []
    auto_merged = {}
    computed_hashes = {}
    stack = [((current_path, merge_result, False))] # Stack stores: (current path, dictionary to process, visited flag)
    objects_dir = repo_dir / ".caf" / "objects"
    while stack:
        current_path, current_dict, visited = stack.pop()


        if not visited:
            stack.append((current_path, current_dict, True))
            # Find all sub-directories and push them onto the stack to process them first
            for name, value in current_dict.items():
                if isinstance(value, dict):
                    full_path = f"{current_path}/{name}" if current_path else name
                    stack.append((full_path, value, False))
        else:
            records = {}
            has_conflict_in_dir = False
           
            for name, value in current_dict.items():
                full_path = f"{current_path}/{name}" if current_path else name
               
                if isinstance(value, TreeRecord):
                    records[name] = value
                elif isinstance(value, dict):
                    if not full_path in computed_hashes:
                        has_conflict_in_dir = True
                    else:
                        records[name] = TreeRecord(TreeRecordType.TREE, computed_hashes[full_path], name)
                elif isinstance(value, MergeConflict):
                    if value.conflict_type == "content":
                        if is_binary_blob(objects_dir / value.ours_hash[:2] / value.ours_hash) or is_binary_blob(objects_dir / value.theirs_hash[:2] / value.theirs_hash):
                            # For binary files, we can't auto-merge, so we just record the conflict
                            conflicts.append((full_path, value))
                            has_conflict_in_dir = True
                        else:
                           #TODO: Complete three way merge
                            pass
                               
                    else:
                        conflicts.append((full_path, value))
                        has_conflict_in_dir = True
            if not has_conflict_in_dir:
                # If there are no conflicts in this directory, we can save it immediately
                tree = Tree(records)
                save_tree(objects_dir, tree)
                computed_hashes[current_path] = hash_object(tree)
   
    root_hash = computed_hashes.get(current_path)
    if conflicts:
        return root_hash, conflicts, auto_merged
   
    return root_hash, [], auto_merged # Return the hash of the root tree if no conflicts



def three_way_merge(repo_dir: Path, conflict: MergeConflict) -> Optional[str]:
    """
    Resolves a content conflict by writing the three versions to disk and returning a new hash.
    """
    pass

def is_binary_blob(blob_path: Path) -> bool:
    """
    Helper function to determine if a blob is binary (for content conflicts).
    """
    pass
    