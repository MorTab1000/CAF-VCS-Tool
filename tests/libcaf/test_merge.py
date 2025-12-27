from libcaf.repository import Repository
from libcaf.merge_algo import find_lca


def test_lca_simple_linear(temp_repo: Repository):
    """
    Test Linear History:
    C1 -> C2 -> C3 (Head A)
    """
    # Setup commits manually or via helper
    c1 = temp_repo.commit_working_dir("Auth", "C1")
    
    # Update HEAD to C1 to make next commit parent C1
    # (Assuming you have a helper or manual Ref update here)
    # For this test, let's assume commit_working_dir auto-updates HEAD
    
    c2 = temp_repo.commit_working_dir("Auth", "C2") # Parent is C1
    c3 = temp_repo.commit_working_dir("Auth", "C3") # Parent is C2
    
    assert find_lca(temp_repo.objects_dir(), c3, c2) == c2
    assert find_lca(temp_repo.objects_dir(), c1, c2) == c1

def test_lca_branching(temp_repo: Repository):
    """
    Test Y-Shape:
            -> A1 (Head A)
    Base ->
            -> B1 (Head B)
    """
    
    base = temp_repo.commit_working_dir("Auth", "Base")
        
    # A1 parent is Base
    a1 = temp_repo.commit_working_dir("Auth", "A1")

    # Simulate B1 parent is Base commit by manually changing HEAD to be Base (instead of A1)
    temp_repo.update_head(base)
    b1 = temp_repo.commit_working_dir("Auth", "B1")
    
    assert find_lca(temp_repo.objects_dir(), a1, b1) == base
    