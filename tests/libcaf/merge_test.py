from libcaf.repository import Repository

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
    
    # Check LCA of C3 and C2 -> Should be C2
    from libcaf.merge_algo import find_lca
    assert find_lca(temp_repo, c3, c2) == c2

def test_lca_branching(temp_repo: Repository):
    """
    Test Y-Shape:
          /-> A1 (Head A)
    Base 
          \-> B1 (Head B)
    """
    # Create Base
    base = temp_repo.commit_working_dir("Auth", "Base")
    
    # Create Branch A (Manually verify HEAD points to Base first)
    
    # Simulate A1 parent is Base
    a1 = temp_repo.commit_working_dir("Auth", "A1")

    # Simulate B1 parent is Base
    (temp_repo.repo_path() / 'HEAD').write_text(base)
    print("-------------------------------------------------")
    print(base)
    b1 = temp_repo.commit_working_dir("Auth", "B1")
    
    from libcaf.merge_algo import find_lca
    assert find_lca(temp_repo, a1, b1) == base