import pytest
import shutil
from datetime import datetime
from libcaf.repository import Repository, MergeResult, RepositoryError, branch_ref
from libcaf.merge_algo import find_lca, MergeConflict, TreeRecordType
from libcaf import Commit
from libcaf.plumbing import save_commit, hash_object, load_commit, open_content_for_reading, load_tree


def _set_working_tree_files(temp_repo: Repository, files: dict[str, str]) -> None:
    """Replace working tree files (excluding .caf) with a deterministic snapshot."""
    for item in temp_repo.working_dir.iterdir():
        if item.name == temp_repo.repo_dir.name:
            continue

        if item.is_dir():
            shutil.rmtree(item)
        else:
            item.unlink()

    for rel_path, content in files.items():
        file_path = temp_repo.working_dir / rel_path
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(content)


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
        temp_repo.merge(hash_a, hash_b, "Author")

def test_merge_already_up_to_date(temp_repo: Repository):
    """
    Case 2: Up-to-date.
    Merging a branch that is already an ancestor of the current branch should result in UP_TO_DATE.
    """
    (temp_repo.working_dir / "base.txt").write_text("base")
    base_hash = temp_repo.commit_working_dir("Author", "Base")
    
    (temp_repo.working_dir / "new.txt").write_text("new")
    head_hash = temp_repo.commit_working_dir("Author", "Forward")

    report = temp_repo.merge(head_hash, base_hash, "Author")
    
    assert report.status == MergeResult.UP_TO_DATE
    assert report.commit_hash == head_hash


def test_merge_fast_forward(temp_repo: Repository):
    """
    Case 3: Fast-forward.
    The source branch is a descendant of target. Result should be FAST_FORWARD pointing to source.
    """
    (temp_repo.working_dir / "base.txt").write_text("base")
    base_hash = temp_repo.commit_working_dir("Author", "Base")
    
    (temp_repo.working_dir / "feature.txt").write_text("feature")
    feature_hash = temp_repo.commit_working_dir("Author", "Feature")

    report = temp_repo.merge(base_hash, feature_hash, "Author")

    assert report.status == MergeResult.FAST_FORWARD
    assert report.commit_hash == feature_hash


def test_merge_invalid_commit(temp_repo: Repository):
    """
    Case: Invalid Source Commit.
    Attempting to merge a non-existent commit hash should raise RepositoryError.
    """
    (temp_repo.working_dir / "init.txt").write_text("init")
    base_hash = temp_repo.commit_working_dir("Author", "Init")
    
    fake_hash = "0" * 40

    with pytest.raises(RepositoryError):
        temp_repo.merge(base_hash, fake_hash, "Author")


def test_merge_3way_clean_different_files(temp_repo: Repository) -> None:
    """3-way clean merge where each side changes a different file."""
    _set_working_tree_files(temp_repo, {
        'file_a.txt': 'base a\n',
        'file_b.txt': 'base b\n',
    })
    base_hash = temp_repo.commit_working_dir('Author', 'base')

    temp_repo.add_branch('feature')
    temp_repo.update_ref('heads/feature', base_hash)

    temp_repo.update_head(branch_ref('main'))
    _set_working_tree_files(temp_repo, {
        'file_a.txt': 'target changed a\n',
        'file_b.txt': 'base b\n',
    })
    target_hash = temp_repo.commit_working_dir('Author', 'target changes file_a')

    temp_repo.update_head(branch_ref('feature'))
    _set_working_tree_files(temp_repo, {
        'file_a.txt': 'base a\n',
        'file_b.txt': 'source changed b\n',
    })
    source_hash = temp_repo.commit_working_dir('Author', 'source changes file_b')

    report = temp_repo.merge(target_hash, source_hash, 'Test Author')

    assert report.status == MergeResult.MERGE_CREATED

    merged_commit = load_commit(temp_repo.objects_dir(), report.commit_hash)
    assert report.commit_hash == hash_object(merged_commit)
    assert merged_commit.parents == [target_hash, source_hash]

    root_tree = load_tree(temp_repo.objects_dir(), merged_commit.tree_hash)

    assert 'file_a.txt' in root_tree.records
    assert 'file_b.txt' in root_tree.records

    blob_a_hash = root_tree.records['file_a.txt'].hash
    blob_b_hash = root_tree.records['file_b.txt'].hash
    
    blob_a_content = (temp_repo.objects_dir() / blob_a_hash[:2] / blob_a_hash).read_bytes()
    blob_b_content = (temp_repo.objects_dir() / blob_b_hash[:2] / blob_b_hash).read_bytes()
    
    assert b'target changed a' in blob_a_content
    assert b'source changed b' in blob_b_content


def test_merge_3way_auto_merge_same_file(temp_repo: Repository) -> None:
    """3-way merge auto-merges non-overlapping edits in the same text file."""
    base_text = '\n'.join([
        'line 1 base',
        'line 2 base',
        'line 3 base',
        'line 4 base',
        'line 5 base',
    ]) + '\n'
    target_text = '\n'.join([
        'line 1 target',
        'line 2 base',
        'line 3 base',
        'line 4 base',
        'line 5 base',
    ]) + '\n'
    source_text = '\n'.join([
        'line 1 base',
        'line 2 base',
        'line 3 base',
        'line 4 base',
        'line 5 source',
    ]) + '\n'

    _set_working_tree_files(temp_repo, {'text.txt': base_text})
    base_hash = temp_repo.commit_working_dir('Author', 'base text')

    temp_repo.add_branch('feature')
    temp_repo.update_ref('heads/feature', base_hash)

    temp_repo.update_head(branch_ref('main'))
    _set_working_tree_files(temp_repo, {'text.txt': target_text})
    target_hash = temp_repo.commit_working_dir('Author', 'target updates line 1')

    temp_repo.update_head(branch_ref('feature'))
    _set_working_tree_files(temp_repo, {'text.txt': source_text})
    source_hash = temp_repo.commit_working_dir('Author', 'source updates line 5')

    report = temp_repo.merge(target_hash, source_hash, 'Test Author')

    assert report.status == MergeResult.MERGE_CREATED
    merged_commit = load_commit(temp_repo.objects_dir(), report.commit_hash)
    assert report.commit_hash == hash_object(merged_commit)
    assert merged_commit.parents == [target_hash, source_hash]

    root_tree = load_tree(temp_repo.objects_dir(), merged_commit.tree_hash)
    assert 'text.txt' in root_tree.records
    assert 'text.txt' in report.auto_merged

    merged_blob_hash = report.auto_merged['text.txt']
    with open_content_for_reading(temp_repo.objects_dir(), merged_blob_hash) as merged_blob:
        merged_text = merged_blob.read().decode('utf-8')

    assert 'line 1 target' in merged_text
    assert 'line 5 source' in merged_text


def test_merge_3way_with_conflicts(temp_repo: Repository) -> None:
    """3-way merge reports conflicts and keeps the working directory untouched."""
    _set_working_tree_files(temp_repo, {'data.txt': 'line1\nbase line\nline3\n'})
    base_hash = temp_repo.commit_working_dir('Author', 'base data')

    temp_repo.add_branch('feature')
    temp_repo.update_ref('heads/feature', base_hash)

    temp_repo.update_head(branch_ref('main'))
    _set_working_tree_files(temp_repo, {'data.txt': 'line1\ntarget value\nline3\n'})
    target_hash = temp_repo.commit_working_dir('Author', 'target conflicting change')

    temp_repo.update_head(branch_ref('feature'))
    _set_working_tree_files(temp_repo, {'data.txt': 'line1\nsource value\nline3\n'})
    source_hash = temp_repo.commit_working_dir('Author', 'source conflicting change')

    before_merge_text = (temp_repo.working_dir / 'data.txt').read_text()
    report = temp_repo.merge(target_hash, source_hash, 'Test Author')

    assert report.status == MergeResult.CONFLICTS
    assert report.commit_hash == target_hash
    target_commit = load_commit(temp_repo.objects_dir(), report.commit_hash)
    assert report.commit_hash == hash_object(target_commit)

    target_tree = load_tree(temp_repo.objects_dir(), target_commit.tree_hash)
    assert 'data.txt' in target_tree.records

    target_blob_hash = target_tree.records['data.txt'].hash
    target_blob_content = (temp_repo.objects_dir() / target_blob_hash[:2] / target_blob_hash).read_bytes()
    assert b'target value' in target_blob_content
    assert any(path == 'data.txt' for path, _ in report.conflicts)

    after_merge_text = (temp_repo.working_dir / 'data.txt').read_text()
    assert after_merge_text == before_merge_text
    assert '<<<<<<<' not in after_merge_text
    assert not temp_repo.merge_head_file().exists()


def test_apply_conflicts_empty_conflicts(temp_repo: Repository) -> None:
    """Applying an empty conflict list should be a no-op."""
    
    _set_working_tree_files(temp_repo, {
        'file_a.txt': 'a\n',
    })
    source_hash = temp_repo.commit_working_dir('Author', 'source commit')
    temp_repo.apply_conflicts_to_disk([], source_hash)
    assert len(list(temp_repo.working_dir.iterdir())) == 2  # .caf + file_a.txt
    assert not temp_repo.merge_head_file().exists()
    assert (temp_repo.working_dir / 'file_a.txt').exists()
    assert (temp_repo.working_dir / 'file_a.txt').read_text() == 'a\n'


def test_apply_conflicts_modify_delete(temp_repo: Repository) -> None:
    """Test modify/delete conflict where ours deleted the file, but theirs modified it."""
    _set_working_tree_files(temp_repo, {"file_a.txt": "original content\n"})
    base_hash = temp_repo.commit_working_dir('Author', 'base commit')
    base_commit = load_commit(temp_repo.objects_dir(), base_hash)
    base_tree = load_tree(temp_repo.objects_dir(), base_commit.tree_hash)
    blob_hash = base_tree.records['file_a.txt'].hash

    _set_working_tree_files(temp_repo, {"file_a.txt": "modified content\n"})
    source_hash = temp_repo.commit_working_dir('Author', 'source modifies file_a')

    source_commit = load_commit(temp_repo.objects_dir(), source_hash)
    source_tree = load_tree(temp_repo.objects_dir(), source_commit.tree_hash)
    modified_blob_hash = source_tree.records['file_a.txt'].hash

    temp_repo.update_head(base_hash)
    _set_working_tree_files(temp_repo, {}) 
    
    temp_repo.commit_working_dir('Author', 'target deletes file_a')

    conflicts = [
        (
            "file_a.txt",
            MergeConflict(
                base_hash=blob_hash, 
                ours_hash=None, 
                theirs_hash=modified_blob_hash, 
                conflict_type="modify/delete",
                ours_type=None,
                theirs_type=TreeRecordType.BLOB
            )
        )
    ]

    temp_repo.apply_conflicts_to_disk(conflicts, source_hash)

    assert len(list(temp_repo.working_dir.iterdir())) == 2
    assert (temp_repo.working_dir / 'file_a.txt').exists()
    assert (temp_repo.working_dir / 'file_a.txt').read_text() == 'modified content\n'
    assert temp_repo.merge_head_file().exists()


def test_apply_conflicts_type_conflict(temp_repo: Repository) -> None:
    """Test type conflict where ours has a file and theirs has a directory with the same name."""

    _set_working_tree_files(temp_repo, {"item": "file content\n"})
    base_hash = temp_repo.commit_working_dir('Author', 'base commit')
    base_commit = load_commit(temp_repo.objects_dir(), base_hash)
    blob_hash = load_tree(temp_repo.objects_dir(), base_commit.tree_hash).records['item'].hash

    _set_working_tree_files(temp_repo, {"item": "modified content\n"}) 
    target_hash = temp_repo.commit_working_dir('Author', 'target modifies item')
    target_commit = load_commit(temp_repo.objects_dir(), target_hash)
    target_modified_blob_hash = load_tree(temp_repo.objects_dir(), target_commit.tree_hash).records['item'].hash
    
    temp_repo.update_head(base_hash)
    (temp_repo.working_dir / 'item').unlink()
    (temp_repo.working_dir / 'item').mkdir()
    (temp_repo.working_dir / 'item' / 'nested.txt').write_text('nested content\n')
    
    source_hash = temp_repo.commit_working_dir('Author', 'source creates directory item')
    source_commit = load_commit(temp_repo.objects_dir(), source_hash)
    source_modified_blob_hash = load_tree(temp_repo.objects_dir(), source_commit.tree_hash).records['item'].hash

    
    shutil.rmtree(temp_repo.working_dir / 'item') # Clean up the source directory
    _set_working_tree_files(temp_repo, {"item": "modified content\n"}) # Restore our file
    temp_repo.update_head(target_hash)

    conflicts = [
        (
            "item",
            MergeConflict(
                base_hash=blob_hash, 
                ours_hash=target_modified_blob_hash, 
                theirs_hash=source_modified_blob_hash, 
                conflict_type="type",
                ours_type=TreeRecordType.BLOB,
                theirs_type=TreeRecordType.TREE
            )
        )
    ]

    temp_repo.apply_conflicts_to_disk(conflicts, source_hash)

    assert (temp_repo.working_dir / 'item').exists()
    assert (temp_repo.working_dir / 'item').is_dir()  
    assert (temp_repo.working_dir / 'item' / 'nested.txt').exists()
    assert (temp_repo.working_dir / 'item' / 'nested.txt').read_text() == 'nested content\n'
    assert (temp_repo.working_dir / 'item~HEAD').exists()
    assert (temp_repo.working_dir / 'item~HEAD').is_file()
    assert (temp_repo.working_dir / 'item~HEAD').read_text() == 'modified content\n'
    assert temp_repo.merge_head_file().exists()


def test_apply_conflicts_modify_modify_same_file(temp_repo: Repository) -> None:
    """Test modify/modify conflict where both sides modified the same file."""
    _set_working_tree_files(temp_repo, {"file_a.txt": "original content\n"})
    base_hash = temp_repo.commit_working_dir('Author', 'base commit')
    base_commit = load_commit(temp_repo.objects_dir(), base_hash)
    base_tree = load_tree(temp_repo.objects_dir(), base_commit.tree_hash)
    blob_hash = base_tree.records['file_a.txt'].hash

    _set_working_tree_files(temp_repo, {"file_a.txt": "target content\n"})
    target_hash = temp_repo.commit_working_dir('Author', 'target modifies file_a')

    target_commit = load_commit(temp_repo.objects_dir(), target_hash)
    target_tree = load_tree(temp_repo.objects_dir(), target_commit.tree_hash)
    target_modified_blob_hash = target_tree.records['file_a.txt'].hash

    temp_repo.update_head(target_hash)
    _set_working_tree_files(temp_repo, {"file_a.txt": "target content\n"})

    _set_working_tree_files(temp_repo, {"file_a.txt": "source content\n"})
    
    source_hash = temp_repo.commit_working_dir('Author', 'source modifies file_a')

    source_commit = load_commit(temp_repo.objects_dir(), source_hash)
    source_tree = load_tree(temp_repo.objects_dir(), source_commit.tree_hash)
    source_modified_blob_hash = source_tree.records['file_a.txt'].hash

    conflicts = [
        (
            "file_a.txt",
            MergeConflict(
                base_hash=blob_hash, 
                ours_hash=target_modified_blob_hash, 
                theirs_hash=source_modified_blob_hash, 
                conflict_type="content",
                ours_type=TreeRecordType.BLOB,
                theirs_type=TreeRecordType.BLOB
            )
        )
    ]

    temp_repo.apply_conflicts_to_disk(conflicts, source_hash)

    assert (temp_repo.working_dir / 'file_a.txt').exists()
    merged_file = (temp_repo.working_dir / 'file_a.txt').read_bytes()
    assert b"<<<<<<< HEAD (ours)\n" in merged_file
    assert b"target content\n" in merged_file
    assert b"=======\n" in merged_file
    assert b"source content\n" in merged_file
    assert b">>>>>>> MERGE_HEAD (theirs)\n" in merged_file

    assert temp_repo.merge_head_file().exists()


def test_apply_conflicts_multiple_conflicts(temp_repo: Repository) -> None:
    """ Test multiple conflicts of different types in the same merge."""
    _set_working_tree_files(temp_repo, {"a": "base a\n", "b": "base b\n", "c": "base c\n"})
    base_hash = temp_repo.commit_working_dir('Author', 'base commit')
    base_commit = load_commit(temp_repo.objects_dir(), base_hash)
    base_tree = load_tree(temp_repo.objects_dir(), base_commit.tree_hash)
    blob_hash_a = base_tree.records['a'].hash
    blob_hash_b = base_tree.records['b'].hash
    blob_hash_c = base_tree.records['c'].hash

    _set_working_tree_files(temp_repo, {"a": "target a\n", "b": "target b\n"})
    (temp_repo.working_dir / 'c').mkdir()
    (temp_repo.working_dir / 'c' / 'nested.txt').write_text('nested content\n')

    target_hash = temp_repo.commit_working_dir('Author', 'target modifies a and b and changes c to a directory')
    target_commit = load_commit(temp_repo.objects_dir(), target_hash)
    target_tree = load_tree(temp_repo.objects_dir(), target_commit.tree_hash)
    target_blob_hash_a = target_tree.records['a'].hash
    target_blob_hash_b = target_tree.records['b'].hash
    target_blob_hash_c = target_tree.records['c'].hash

    temp_repo.update_head(base_hash)
    shutil.rmtree(temp_repo.working_dir / 'c')
    _set_working_tree_files(temp_repo, {"b": "source b\n", "c": "source c\n"})
    if (temp_repo.working_dir / 'a').exists():
        (temp_repo.working_dir / 'a').unlink()
    source_hash = temp_repo.commit_working_dir('Author', 'source deletes a and modifies b and c')
    source_commit = load_commit(temp_repo.objects_dir(), source_hash)
    source_tree = load_tree(temp_repo.objects_dir(), source_commit.tree_hash)
    source_blob_hash_b = source_tree.records['b'].hash
    source_blob_hash_c = source_tree.records['c'].hash

    conflicts = [
        (
            "a",
            MergeConflict(
                base_hash=blob_hash_a, 
                ours_hash=target_blob_hash_a, 
                theirs_hash=None, 
                conflict_type="modify/delete",
                ours_type=TreeRecordType.BLOB,
                theirs_type=None
            )
        ),
        (
            "b",
            MergeConflict(
                base_hash=blob_hash_b, 
                ours_hash=target_blob_hash_b, 
                theirs_hash=source_blob_hash_b, 
                conflict_type="content",
                ours_type=TreeRecordType.BLOB,
                theirs_type=TreeRecordType.BLOB
            )
        ),
        (
            "c",
            MergeConflict(
                base_hash=blob_hash_c, 
                ours_hash=target_blob_hash_c, 
                theirs_hash=source_blob_hash_c, 
                conflict_type="type",
                ours_type=TreeRecordType.TREE,
                theirs_type=TreeRecordType.BLOB
            )
        )
    ]

    #reset back to target state:
    _set_working_tree_files(temp_repo, {"a": "target a\n", "b": "target b\n"})
    (temp_repo.working_dir / 'c').mkdir()
    (temp_repo.working_dir / 'c' / 'nested.txt').write_text('nested content\n')

    temp_repo.apply_conflicts_to_disk(conflicts, source_hash)

    


    assert (temp_repo.working_dir / 'a').exists()
    assert (temp_repo.working_dir / 'a').is_file()
    assert (temp_repo.working_dir / 'a').read_text() == 'target a\n'

    assert (temp_repo.working_dir / 'b').exists()
    merged_b_content = (temp_repo.working_dir / 'b').read_bytes()
    assert b"<<<<<<< HEAD (ours)\n" in merged_b_content
    assert b"target b\n" in merged_b_content
    assert b"=======\n" in merged_b_content
    assert b"source b\n" in merged_b_content
    assert b">>>>>>> MERGE_HEAD (theirs)\n" in merged_b_content

    assert (temp_repo.working_dir / 'c').exists()
    assert (temp_repo.working_dir / 'c').is_dir()
    assert (temp_repo.working_dir / 'c' / 'nested.txt').exists()
    assert (temp_repo.working_dir / 'c' / 'nested.txt').read_text() == 'nested content\n'
    assert (temp_repo.working_dir / 'c~MERGE_HEAD').exists()
    assert (temp_repo.working_dir / 'c~MERGE_HEAD').is_file()
    assert (temp_repo.working_dir / 'c~MERGE_HEAD').read_text() == 'source c\n'

    assert temp_repo.merge_head_file().exists()


def test_apply_conflicts_binary_content(temp_repo: Repository) -> None:
    """Test content conflict on binary files (e.g., images). Theirs should be extracted as ~MERGE_HEAD.""" 
    binary_file = temp_repo.working_dir / 'logo.png'
    binary_file.write_bytes(b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR base')
    base_hash = temp_repo.commit_working_dir('Author', 'base commit')
    base_commit = load_commit(temp_repo.objects_dir(), base_hash)
    blob_hash_base = load_tree(temp_repo.objects_dir(), base_commit.tree_hash).records['logo.png'].hash

    binary_file.write_bytes(b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR target')
    target_hash = temp_repo.commit_working_dir('Author', 'target modifies logo')
    target_commit = load_commit(temp_repo.objects_dir(), target_hash)
    blob_hash_target = load_tree(temp_repo.objects_dir(), target_commit.tree_hash).records['logo.png'].hash

    temp_repo.update_head(base_hash)
    binary_file.write_bytes(b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR source')
    source_hash = temp_repo.commit_working_dir('Author', 'source modifies logo')
    source_commit = load_commit(temp_repo.objects_dir(), source_hash)
    blob_hash_source = load_tree(temp_repo.objects_dir(), source_commit.tree_hash).records['logo.png'].hash

    temp_repo.update_head(target_hash)
    binary_file.write_bytes(b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR target')

    conflicts = [
        (
            "logo.png",
            MergeConflict(
                base_hash=blob_hash_base, 
                ours_hash=blob_hash_target, 
                theirs_hash=blob_hash_source, 
                conflict_type="content",
                ours_type=TreeRecordType.BLOB,
                theirs_type=TreeRecordType.BLOB
            )
        )
    ]

    temp_repo.apply_conflicts_to_disk(conflicts, source_hash)

    assert binary_file.exists()
    assert binary_file.read_bytes() == b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR target'
    
    sidecar_file = temp_repo.working_dir / 'logo.png~MERGE_HEAD'
    assert sidecar_file.exists()
    assert sidecar_file.read_bytes() == b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR source'
    
    assert temp_repo.merge_head_file().exists()