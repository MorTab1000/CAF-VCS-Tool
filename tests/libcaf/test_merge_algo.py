from libcaf import Tree, TreeRecord, TreeRecordType
from libcaf.plumbing import load_tree
from libcaf.repository import Repository
from libcaf.merge_algo import merge_trees, MergeConflict, compute_merge_tree, three_way_merge
from pathlib import Path
import hashlib




def quick_blob(objects_dir: Path, content: bytes) -> str:
    # This simulates saving a blob and getting its hash
    h = hashlib.sha1(content).hexdigest()
    obj_path = objects_dir / h[:2] / h
    obj_path.parent.mkdir(parents=True, exist_ok=True)
    obj_path.write_bytes(content) # Simulating raw storage as we discussed
    return h




def test_identical_roots() -> None:
    fake_db ={"base_root" : Tree({"file.txt": TreeRecord(TreeRecordType.BLOB, "h1", "file.txt")})}
   
    result = merge_trees("base_root", "base_root", "base_root", lambda h: fake_db[h])
    assert result == {"file.txt": TreeRecord(TreeRecordType.BLOB, "h1", "file.txt")}




def test_fast_forward_ours_root() -> None:
    fake_db = { "base_root" : Tree({"file.txt": TreeRecord(TreeRecordType.BLOB, "h1", "file.txt")}),
                "ours_root" :  Tree({"file.txt": TreeRecord(TreeRecordType.BLOB, "h2", "file.txt")})
    }      
    result = merge_trees("base_root", "ours_root", "base_root", lambda h: fake_db[h])
   
    assert result == {"file.txt": TreeRecord(TreeRecordType.BLOB, "h2", "file.txt")}




def test_fast_forward_theirs_root() -> None:
    fake_db = { "base_root" : Tree({"file.txt": TreeRecord(TreeRecordType.BLOB, "h1", "file.txt")}),
                "theirs_root" :  Tree({"file.txt": TreeRecord(TreeRecordType.BLOB, "h2", "file.txt")})
    }
    result = merge_trees("base_root", "base_root", "theirs_root", lambda h: fake_db[h])
   
    assert result == {"file.txt": TreeRecord(TreeRecordType.BLOB, "h2", "file.txt")}




def test_mutual_deletion() -> None:
    fake_db = {
        "base_root": Tree({"file.txt": TreeRecord(TreeRecordType.BLOB, "h1", "file.txt")}),
        "ours_root": Tree({}),
        "theirs_root": Tree({})
    }


    result = merge_trees("base_root", "ours_root", "theirs_root", lambda h: fake_db[h])
   
    assert result == {}




def test_content_conflict() -> None:
    fake_db = {
        "base_root": Tree({"file.txt": TreeRecord(TreeRecordType.BLOB, "h1", "file.txt")}),
        "ours_root": Tree({"file.txt": TreeRecord(TreeRecordType.BLOB, "h2", "file.txt")}),
        "theirs_root": Tree({"file.txt": TreeRecord(TreeRecordType.BLOB, "h3", "file.txt")})
    }


    result = merge_trees("base_root", "ours_root", "theirs_root", lambda h: fake_db[h])


    assert result == {"file.txt": MergeConflict("h1", "h2", "h3", "content")}
   
   




def test_modify_delete_conflict() -> None:
    fake_db = {
        "base_root": Tree({"file.txt": TreeRecord(TreeRecordType.BLOB, "h1", "file.txt")}),
        "ours_root": Tree({"file.txt": TreeRecord(TreeRecordType.BLOB, "h2", "file.txt")}),
        "theirs_root": Tree({})
    }


    result = merge_trees("base_root", "ours_root", "theirs_root", lambda h: fake_db[h])
   
    assert result == {"file.txt": MergeConflict("h1", "h2", None, "modify/delete")}




def test_file_dir_conflict() -> None:
    fake_db = {
        "base_root": Tree({}),
        "ours_root": Tree({"logger": TreeRecord(TreeRecordType.BLOB, "h_file", "logger")}),
        "theirs_root": Tree({"logger": TreeRecord(TreeRecordType.TREE, "h_dir", "logger")})
    }


    result = merge_trees("base_root", "ours_root", "theirs_root", lambda h: fake_db[h])
   
    assert result == {"logger": MergeConflict(None, "h_file", "h_dir", "type")}




def test_directory_recursion() -> None:
    fake_db = {
        "base_src": Tree({
            "a.txt": TreeRecord(TreeRecordType.BLOB, "h_a", "a.txt"),
            "b.txt": TreeRecord(TreeRecordType.BLOB, "h_b", "b.txt")
        }),
        "ours_src": Tree({
            "a.txt": TreeRecord(TreeRecordType.BLOB, "h_a_mod", "a.txt"),
            "b.txt": TreeRecord(TreeRecordType.BLOB, "h_b", "b.txt")
        }),
        "theirs_src": Tree({
            "a.txt": TreeRecord(TreeRecordType.BLOB, "h_a", "a.txt"),
            "b.txt": TreeRecord(TreeRecordType.BLOB, "h_b_mod", "b.txt")
        }),
        "base_root": Tree({"src": TreeRecord(TreeRecordType.TREE, "base_src", "src")}),
        "ours_root": Tree({"src": TreeRecord(TreeRecordType.TREE, "ours_src", "src")}),
        "theirs_root": Tree({"src": TreeRecord(TreeRecordType.TREE, "theirs_src", "src")})
    }


    result = merge_trees("base_root", "ours_root", "theirs_root", lambda h: fake_db[h])


    assert result == {"src": {"a.txt": TreeRecord(TreeRecordType.BLOB, "h_a_mod", "a.txt"), "b.txt": TreeRecord(TreeRecordType.BLOB, "h_b_mod", "b.txt")}}




def test_compute_merge_tree_clean_files(temp_repo: Repository) -> None:
    plan = {
    "main.py": TreeRecord(TreeRecordType.BLOB, "hash_main", "main.py"),
    "README.md": TreeRecord(TreeRecordType.BLOB, "hash_readme", "README.md")
    }


    new_tree_hash, conflicts, auto_merged = compute_merge_tree(temp_repo.objects_dir(), plan)
   
    assert new_tree_hash is not None
    assert conflicts == []
    assert auto_merged == {}


    folder_prefix = new_tree_hash[:2]
   
    assert (temp_repo.objects_dir() / folder_prefix / new_tree_hash).exists()


def test_compute_merge_nested_directories(temp_repo: Repository) -> None:
    plan = {
        "README.md": TreeRecord(TreeRecordType.BLOB, "hash_readme", "README.md"),
        "src": {
            "main.py": TreeRecord(TreeRecordType.BLOB, "hash_main", "main.py"),
            "utils.py": TreeRecord(TreeRecordType.BLOB, "hash_utils", "utils.py")
        }
    }


    root_tree_hash, conflicts, auto_merged = compute_merge_tree(temp_repo.objects_dir(), plan)


    assert root_tree_hash is not None
    assert conflicts == []
    assert auto_merged == {}
   
    root_folder_prefix = root_tree_hash[:2]
    assert (temp_repo.objects_dir() / root_folder_prefix / root_tree_hash).exists()
   
    new_tree = load_tree(temp_repo.objects_dir(), root_tree_hash)
    src_record = new_tree.records.get("src")
    assert src_record is not None and src_record.type == TreeRecordType.TREE


    src_tree_hash = src_record.hash
    src_folder_prefix = src_tree_hash[:2]
    assert (temp_repo.objects_dir() / src_folder_prefix / src_tree_hash).exists()




def test_compute_merge_with_structural_conflict(temp_repo: Repository) -> None:
    conflict_obj = MergeConflict(
        conflict_type="modify/delete",
        base_hash="hash_base",
        ours_hash="hash_ours",
        theirs_hash=None)
    plan = {
        "clean_file.txt": TreeRecord(TreeRecordType.BLOB, "hash_clean", "clean_file.txt"),
        "nested": {
            "broken_file.txt": conflict_obj
        }
    }
    root_tree_hash, conflicts, auto_merged = compute_merge_tree(temp_repo.objects_dir(), plan)


    assert root_tree_hash is None
    assert conflicts == [("nested/broken_file.txt", conflict_obj)]
    assert auto_merged == {}



def test_compute_merge_with_type_conflict(temp_repo: Repository) -> None:  
    conflict_obj = MergeConflict(
        conflict_type="type",
        base_hash=None,
        ours_hash="hash_blob",
        theirs_hash="hash_tree")
    plan = {
        "conflict_item": conflict_obj
    }
    root_tree_hash, conflicts, auto_merged = compute_merge_tree(temp_repo.objects_dir(), plan)


    assert root_tree_hash is None
    assert conflicts == [("conflict_item", conflict_obj)]
    assert auto_merged == {}


def test_compute_merge_empty_plan(temp_repo: Repository) -> None:
    plan = {}
    root_tree_hash, conflicts, auto_merged = compute_merge_tree(temp_repo.objects_dir(), plan)

    assert root_tree_hash is not None
    assert len(conflicts) == 0
    assert len(auto_merged) == 0
   
    root_folder_prefix = root_tree_hash[:2]
    assert (temp_repo.objects_dir() / root_folder_prefix / root_tree_hash).exists()


def test_compute_merge_complex_structure(temp_repo: Repository) -> None:
    """
    Test a full merge of a directory structure.
    - file1: Clean merge
    - file2: Conflict
    - dir1/file3: Clean merge
    """
    repo_dir = temp_repo.working_dir
    objects_dir = repo_dir / ".caf" / "objects"

    # File 1: Clean merge (Both modified different lines)
    h1_base = quick_blob(objects_dir, b"line1\nline2\nline3\n")
    h1_ours = quick_blob(objects_dir, b"line1 modified\nline2\nline3\n")
    h1_theirs = quick_blob(objects_dir, b"line1\nline2\nline3 modified\n")

    # File 2: Overlapping Conflict
    h2_base = quick_blob(objects_dir, b"common\n")
    h2_ours = quick_blob(objects_dir, b"change A\n")
    h2_theirs = quick_blob(objects_dir, b"change B\n")

    merge_plan = {
        "file1.txt": MergeConflict(h1_base, h1_ours, h1_theirs, "content"),
        "file2.txt": MergeConflict(h2_base, h2_ours, h2_theirs, "content"),
        "folder": {
            "nested.txt": TreeRecord(TreeRecordType.BLOB, h1_ours, "nested.txt") # No conflict here
        }
    }


    # 3. Run the engine
    root_hash, conflicts, auto_merged = compute_merge_tree(temp_repo.objects_dir(), merge_plan)


    # Root should be None because file2.txt has a conflict
    assert root_hash is None
   
    # file1.txt should be in auto_merged
    assert "file1.txt" in auto_merged
   
    f1_content = (objects_dir / auto_merged["file1.txt"][:2] / auto_merged["file1.txt"]).read_bytes()
    assert b"line1 modified\n" in f1_content
    assert b"line2\n" in f1_content
    assert b"line3 modified\n" in f1_content
   
    assert "file2.txt" not in auto_merged
    assert conflicts == [("file2.txt", MergeConflict(h2_base, h2_ours, h2_theirs, "content"))]


def test_three_way_merge_success(temp_repo_dir: Path) -> None:
    """Test a clean merge where changes don't overlap."""
    base = [b"A\n", b"B\n", b"C\n"]
    ours = [b"A (ours)\n", b"B\n", b"C\n"]
    theirs = [b"A\n", b"B\n", b"C (theirs)\n"]

    output_path = temp_repo_dir / "merged_file.txt"
   
    is_clean = three_way_merge(base, ours, theirs, output_path)
   
    assert is_clean is True
    result = output_path.read_bytes()
    assert b"A (ours)\n" in result
    assert b"B\n" in result
    assert b"C (theirs)\n" in result


def test_three_way_merge_conflict_markers(temp_repo_dir: Path) -> None:
    """Test that a conflict results in correct markers and is_clean=False."""
    # Overlapping change on the same line (B)
    base = [b"A\n", b"B\n", b"C\n"]
    ours = [b"A\n", b"B (modified ours)\n", b"C\n"]
    theirs = [b"A\n", b"B (modified theirs)\n", b"C\n"]
   
    output_path = temp_repo_dir / "conflict_file.txt"
   
    is_clean = three_way_merge(base, ours, theirs, output_path)
   
    assert is_clean is False
    result = output_path.read_bytes()
   
    # Check for markers
    assert b"<<<<<<< HEAD (ours)\n" in result
    assert b"B (modified ours)\n" in result
    assert b"=======\n" in result
    assert b"B (modified theirs)\n" in result
    assert b">>>>>>> MERGE_HEAD (theirs)\n" in result




def test_three_way_merge_with_empty_base(temp_repo_dir: Path) -> None:
    """Test merging when the file didn't exist in base (Add/Add conflict)."""
    base = []
    ours = [b"new file content\n"]
    theirs = [b"different content\n"]
   
    output_path = temp_repo_dir / "add_add_conflict.txt"
   
    is_clean = three_way_merge(base, ours, theirs, output_path)
   
    assert is_clean is False
    result = output_path.read_bytes()
    assert b"<<<<<<< HEAD (ours)\n" in result
    assert b"different content\n" in result
    assert b"=======\n" in result
    assert b"new file content\n" in result
    assert b">>>>>>> MERGE_HEAD (theirs)\n" in result