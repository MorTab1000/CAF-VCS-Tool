from libcaf.repository import Repository, branch_ref
from libcaf.ref import SymRef
from libcaf.merge_algo import find_lca
from libcaf import Commit
from libcaf.plumbing import save_commit, hash_object
from datetime import datetime

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
        [] # No parents = Orphan commit
    )
    save_commit(temp_repo.objects_dir(), commit_b)
    commit_b_hash = hash_object(commit_b)
    
    temp_repo.add_branch("other-branch")
    ref_full_path = branch_ref("other-branch")
    # Make the new branch point to commit b
    temp_repo.update_ref(ref_full_path, commit_b_hash)

    try:
        result = temp_repo.merge("other-branch")
        assert "unrelated histories" in result.lower()

    except Exception as e:
        pytest.fail(f"Merge crashed with an unexpected error: {e}")
    
    assert file_a.exists()
    assert file_a.read_text() == "root a"
    assert temp_repo.head_commit() == commit_a_hash

    assert temp_repo.resolve_ref(SymRef("heads/other-branch")) == commit_b_hash


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
    
    try:
        # 'feature' (base) is an ancestor of 'main' (head)
        result = temp_repo.merge("feature")
        assert "already up to date" in result.lower()
        
    except Exception as e:
        pytest.fail(f"Merge crashed with an unexpected error: {e}")

    assert temp_repo.head_commit() == head_commit_hash
    
    # Verify the source branch ('feature') remained unchanged
    assert temp_repo.resolve_ref(SymRef("heads/feature")) == base_commit_hash
    
    # Verify working directory remained unchanged
    assert common_file.exists()
    assert common_file.read_text() == "base content"
    assert main_file.exists()
    assert main_file.read_text() == "main content"


def test_merge_fast_forward_addition(temp_repo: Repository):
    """
    Case 3a: Target (HEAD) is Ancestor of Source (Fast-forward Addition).
    The source branch has a new file. After merging, HEAD should move forward 
    and the working directory must be updated to include the new file.
    """
    common_file = temp_repo.working_dir / "common.txt"
    common_file.write_text("common content")
    base_commit_hash = temp_repo.commit_working_dir("Author", "Common Base")

    # Detach from 'main' branch and verify HEAD is base commit so the two branches will share history
    temp_repo.update_head(base_commit_hash)    
    temp_repo.add_branch("feature")

    # Create a new file commited only in the feature branch and make sure its pointing at it
    feature_file = temp_repo.working_dir / "feature.txt"
    feature_file.write_text("new feature content")
    feature_commit_hash = temp_repo.commit_working_dir("Author", "Feature Work")
    temp_repo.update_ref(branch_ref("feature"), feature_commit_hash)
    
    # Switch back to 'main' which is still at base commit
    temp_repo.update_head(base_commit_hash)
    temp_repo.update_working_directory(base_commit_hash)

    try:
        result = temp_repo.merge("feature")
        assert "fast-forward" in result.lower()
        
    except Exception as e:
        pytest.fail(f"Merge crashed with an unexpected error: {e}")

    assert temp_repo.head_commit() == feature_commit_hash
    assert temp_repo.resolve_ref(SymRef("heads/feature")) == feature_commit_hash
    
    assert feature_file.exists()
    assert feature_file.read_text() == "new feature content"
    assert common_file.exists()
    assert common_file.read_text() == "common content"


# TODO: fix "update_working_directory" to make the test pass
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
    
    temp_repo.update_head(base_hash)
    temp_repo.add_branch("feature")
    
    # In the feature branch delete the file and commit
    if delete_file.exists():
        delete_file.unlink()
        
    feature_commit_hash = temp_repo.commit_working_dir("Author", "Deleted a file")
    temp_repo.update_ref(branch_ref("feature"), feature_commit_hash)
    
    # Switch back to 'main' (base_hash), delete_me.txt should reappear on disk
    temp_repo.update_head(base_hash)
    temp_repo.update_working_directory(base_hash)
    
    assert delete_file.exists(), "Setup failed: file should exist in main before merge"
    
    try:
        result = temp_repo.merge("feature")
        assert "fast-forward" in result.lower()
        
    except Exception as e:
        pytest.fail(f"Merge crashed with an unexpected error: {e}")

    assert temp_repo.head_commit() == feature_commit_hash
    assert temp_repo.resolve_ref(SymRef("heads/feature")) == feature_commit_hash
    
    # CRITICAL: Verify the file was actually deleted from the disk
    # This is where the test is expected to fail until update_working_directory is fixed
    assert not delete_file.exists(), "The file should have been deleted by the merge"
    
    assert common_file.exists()
    assert common_file.read_text() == "i will stay"
