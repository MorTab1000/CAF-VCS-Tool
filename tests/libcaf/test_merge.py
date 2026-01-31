import pytest
from datetime import datetime
from libcaf.ref import HashRef
from libcaf.repository import Repository, MergeResult, RepositoryError
from libcaf.merge_algo import find_lca
from libcaf import Commit
from libcaf.plumbing import save_commit, hash_object


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
    Case 1: Unrelated Histories.
    Merging two branches that do not share a common ancestor should raise NotImplementedError.
    """
    (temp_repo.working_dir / "file_a.txt").write_text("root a")
    hash_a = temp_repo.commit_working_dir("Author", "Root A")

    commit_b = Commit(
        "0000000000000000000000000000000000000001", 
        "Author1", 
        "Root B", 
        int(datetime.now().timestamp()), 
        [] 
    )
    save_commit(temp_repo.objects_dir(), commit_b)
    hash_b = hash_object(commit_b)

    with pytest.raises(NotImplementedError):
        temp_repo.merge(HashRef(hash_a), HashRef(hash_b))

def test_merge_already_up_to_date(temp_repo: Repository):
    """
    Case 2: Up-to-date.
    Merging a branch that is already an ancestor of the current branch should result in UP_TO_DATE.
    """
    (temp_repo.working_dir / "base.txt").write_text("base")
    base_hash = temp_repo.commit_working_dir("Author", "Base")
    
    (temp_repo.working_dir / "new.txt").write_text("new")
    head_hash = temp_repo.commit_working_dir("Author", "Forward")

    result, ref = temp_repo.merge(HashRef(head_hash), HashRef(base_hash))
    
    assert result == MergeResult.UP_TO_DATE
    assert ref == head_hash


def test_merge_fast_forward(temp_repo: Repository):
    """
    Case 3: Fast-forward.
    The source branch is a descendant of target. Result should be FAST_FORWARD pointing to source.
    """
    (temp_repo.working_dir / "base.txt").write_text("base")
    base_hash = temp_repo.commit_working_dir("Author", "Base")
    
    (temp_repo.working_dir / "feature.txt").write_text("feature")
    feature_hash = temp_repo.commit_working_dir("Author", "Feature")

    result, ref = temp_repo.merge(HashRef(base_hash), HashRef(feature_hash))
    
    assert result == MergeResult.FAST_FORWARD
    assert str(ref) == feature_hash


def test_merge_invalid_commit(temp_repo: Repository):
    """
    Case: Invalid Source Commit.
    Attempting to merge a non-existent commit hash should raise RepositoryError.
    """
    (temp_repo.working_dir / "init.txt").write_text("init")
    base_hash = temp_repo.commit_working_dir("Author", "Init")
    
    fake_hash = "0" * 40

    with pytest.raises(RepositoryError):
        temp_repo.merge(HashRef(base_hash), HashRef(fake_hash))
