from libcaf.repository import Repository, branch_ref, RepositoryError, MergeResult, BranchNotFoundError, UnrelatedHistoriesError
from libcaf.ref import SymRef
from libcaf.merge_algo import find_lca
from libcaf import Commit
from libcaf.plumbing import save_commit, hash_object
from datetime import datetime
import pytest
from libcaf.ref import write_ref


def test_lca_simple_linear(temp_repo: Repository):
    """
    Test Linear History:
    C1 -> C2 -> C3 (Head A)
    """
    c1 = temp_repo.commit_working_dir("Author", "C1")
    c2 = temp_repo.commit_working_dir("Author", "C2") # Parent is C1
    c3 = temp_repo.commit_working_dir("Author", "C3") # Parent is C2
    
    assert find_lca(temp_repo.objects_dir(), c3, c2) == c2
    assert find_lca(temp_repo.objects_dir(), c1, c2) == c1

def test_lca_branching(temp_repo: Repository):
    """
    Test Y-Shape:
            -> A1 (Head A)
    Base ->
            -> B1 (Head B)
    """
    
    base = temp_repo.commit_working_dir("Author", "Base")
        
    # A1 parent is Base
    a1 = temp_repo.commit_working_dir("Author", "A1")

    # Simulate B1 parent is Base commit by manually changing HEAD to be Base (instead of A1)
    temp_repo.update_head(base)
    b1 = temp_repo.commit_working_dir("Author", "B1")
    
    assert find_lca(temp_repo.objects_dir(), a1, b1) == base
    

def test_lca_no_common_ancestor(temp_repo: Repository):
    """
    Test No Common Ancestor:
    A1 (Head A)
        
    B1 (Head B)
    """
    commit_a = Commit(
        "0000000000000000000000000000000000000000", 
        "Tester", 
        "Root A", 
        int(datetime.now().timestamp()), 
        [] 
    )
    save_commit(temp_repo.objects_dir(), commit_a)
    hash_a = hash_object(commit_a)

    commit_b = Commit(
        "0000000000000000000000000000000000000000", 
        "Tester", 
        "Root B", 
        int(datetime.now().timestamp()), 
        [] 
    )
    save_commit(temp_repo.objects_dir(), commit_b)
    hash_b = hash_object(commit_b)
        
    assert find_lca(temp_repo.objects_dir(), hash_a, hash_b) is None


def test_merge_unrelated_histories(temp_repo: Repository):
    """
    Case 1: Unrelated Histories (Disjoint).
    The merge should be refused, returning a specific message without changing HEAD.
    """  
    file_a = temp_repo.working_dir / "file_a.txt"
    file_a.write_text("root a")
    commit_a_hash = temp_repo.commit_working_dir("Author", "Root A")

    commit_b = Commit(
        "0000000000000000000000000000000000000001", 
        "Author1", 
        "Root B", 
        int(datetime.now().timestamp()), 
        [] 
    )
    save_commit(temp_repo.objects_dir(), commit_b)
    commit_b_hash = hash_object(commit_b)
    
    temp_repo.add_branch("other-branch")
    ref_full_path = branch_ref("other-branch")
    # Make the new branch point to commit b
    temp_repo.update_ref(ref_full_path, commit_b_hash)
    with pytest.raises(UnrelatedHistoriesError):
        temp_repo.merge("main", "other-branch")

    
    assert file_a.exists()
    assert file_a.read_text() == "root a"
    assert temp_repo.head_commit() == commit_a_hash

    assert temp_repo.resolve_ref(branch_ref("other-branch")) == commit_b_hash


def test_merge_already_up_to_date(temp_repo: Repository):
    """
    Case 2: Source is Ancestor (Already Up-to-date).
    Target (HEAD) already contains the Source branch history.
    """
    common_file = temp_repo.working_dir / "common.txt"
    common_file.write_text("base content")
    base_commit_hash = temp_repo.commit_working_dir("Author", "Base Commit")
    
    temp_repo.add_branch("feature")
    # Verify the branch is pointed to the base commit
    temp_repo.update_ref(branch_ref("feature"), base_commit_hash)
    
    # Advance 'main' branch so it is ahead of 'feature'
    main_file = temp_repo.working_dir / "main_only.txt"
    main_file.write_text("main content")
    head_commit_hash = temp_repo.commit_working_dir("Author", "Main ahead")
    
        # 'feature' (base) is an ancestor of 'main' (head)
    result = temp_repo.merge("main", "feature")
    assert result == MergeResult.UP_TO_DATE
        
    assert temp_repo.head_commit() == head_commit_hash
    
    # Verify the source branch ('feature') remained unchanged
    assert temp_repo.resolve_ref(branch_ref("feature")) == base_commit_hash
    
    # Verify working directory remained unchanged
    assert common_file.exists()
    assert common_file.read_text() == "base content"
    assert main_file.exists()
    assert main_file.read_text() == "main content"


def test_merge_fast_forward_addition(temp_repo: Repository):
    """
    Case 3a: Fast-forward Addition.
    Target (main) is Ancestor of Source (feature).
    The source branch has a new file.
    """
    # Setup Base State (Common Commit)
    common_file = temp_repo.working_dir / "common.txt"
    common_file.write_text("common content")
    base_commit_hash = temp_repo.commit_working_dir("Author", "Common Base")

    # Setup Feature Branch (Feature Commit)
    # Create the new file and commit it
    feature_file = temp_repo.working_dir / "feature.txt"
    feature_file.write_text("new feature content")
    feature_commit_hash = temp_repo.commit_working_dir("Author", "Feature Work")
    
    # Create the 'feature' branch pointing to this new commit
    temp_repo.add_branch("feature")
    temp_repo.update_ref(branch_ref("feature"), feature_commit_hash)
    
    # Reset Environment to 'main' state
    if feature_file.exists():
        feature_file.unlink() 
    
    # Point 'main' and HEAD back to the base commit
    main_ref = branch_ref("main")
    temp_repo.update_ref(main_ref, base_commit_hash)
    write_ref(temp_repo.head_file(), main_ref)


    result = temp_repo.merge("main", "feature")

    assert result == MergeResult.FAST_FORWARD

    # Verify Graph Logic (The pointers moved)
    assert temp_repo.head_commit() == feature_commit_hash
    assert temp_repo.resolve_ref(main_ref) == feature_commit_hash


def test_merge_fast_forward_deletion(temp_repo: Repository):
    """
    Case 3b: Fast-forward with Deletion.
    The source branch deleted a file. After merging, 
    that file should also be removed from the target's working directory.
    """
    common_file = temp_repo.working_dir / "stay.txt"
    delete_file = temp_repo.working_dir / "delete_me.txt"
    
    common_file.write_text("i will stay")
    delete_file.write_text("i will be deleted")
    
    base_hash = temp_repo.commit_working_dir("Author", "Base with two files")
    
    temp_repo.add_branch("feature")
    
    # In the feature branch delete the file and commit
    if delete_file.exists():
        delete_file.unlink()
        
    feature_commit_hash = temp_repo.commit_working_dir("Author", "Deleted a file")
    temp_repo.update_ref(branch_ref("feature"), feature_commit_hash)
    
    # Switch back to 'main' (base_hash), delete_me.txt should reappear on disk
    # Reset Environment to 'main' state
    # Manually recreate the file to simulate being back at base
    delete_file.write_text("i will be deleted")
    main_ref = branch_ref("main") 
    temp_repo.update_ref(main_ref, base_hash)           
    write_ref(temp_repo.head_file(), main_ref)
    assert delete_file.exists(), "Setup failed: file should exist in main before merge"

    result = temp_repo.merge("main", "feature")
    assert result == MergeResult.FAST_FORWARD
        
    assert temp_repo.head_commit() == feature_commit_hash
    assert temp_repo.resolve_ref(main_ref) == feature_commit_hash


def test_merge_non_existent_branch(temp_repo: Repository):
    """
    Case: Non-existent Branch.
    Attempting to merge a branch that does not exist should raise a RepositoryError.
    """
    (temp_repo.working_dir / "init.txt").write_text("initial")
    temp_repo.commit_working_dir("Author", "Initial commit")

    # Try to merge a branch that was never created. We expect the custom RepositoryError to be raised
    with pytest.raises(BranchNotFoundError) as excinfo:
        temp_repo.merge("main", "ghost-branch")


    # Verify HEAD didn't move or change (since the merge shouldn't have even started)
    assert len(temp_repo.branches()) == 1
    assert temp_repo.branches()[0] == "main" # Assuming default branch is main
