
from libcaf import Tree, TreeRecord, TreeRecordType
from libcaf.merge_algo import merge_trees, MergeConflict




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