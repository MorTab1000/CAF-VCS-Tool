from libcaf.ref import SymRef
from libcaf.repository import Repository, branch_ref
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