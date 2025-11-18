from pathlib import Path   
from libcaf.constants import TAGS_DIR, REFS_DIR, DEFAULT_REPO_DIR
from libcaf.repository import Repository, RepositoryError
from pytest import raises



def test_tags_dir(temp_repo: Repository) -> None:
    temp_file = temp_repo.working_dir / "file.txt"
    temp_file.write_text("Sample content")
    commit_hash = temp_repo.commit_working_dir("tester", "initial commit")

    temp_repo.create_tag("v1.0", commit_hash)

    assert temp_repo.tag_exists("v1.0")

    tag_path = temp_repo.working_dir / DEFAULT_REPO_DIR / REFS_DIR / TAGS_DIR / "v1.0"
    assert tag_path.exists()
    assert tag_path.read_text().strip() == commit_hash

def test_creating_an_existing_tag_raises_error(temp_repo: Repository) -> None:
    temp_file = temp_repo.working_dir / "file.txt"
    temp_file.write_text("Sample content")
    commit_hash = temp_repo.commit_working_dir("tester", "initial commit")

    temp_repo.create_tag("v1.0", commit_hash)

    with raises(RepositoryError):
        temp_repo.create_tag("v1.0", commit_hash)

def test_creating_tag_on_nonexistent_commit_raises_error(temp_repo: Repository) -> None:
    with raises(RepositoryError):
        temp_repo.create_tag("v1.0", "1754567890abcdef1234567890abcdef12345678")

def test_delete_tag(temp_repo: Repository) -> None:
    temp_repo.working_dir.joinpath('test_file').write_text('content')
    commit_ref = temp_repo.commit_working_dir('Author', 'Message')
    temp_repo.create_tag('v1.0', commit_ref)

    temp_repo.delete_tag('v1.0')
    assert not temp_repo.tag_exists('v1.0')

def test_delete_nonexistent_tag_raises_error(temp_repo: Repository) -> None:
    with raises(RepositoryError, match='does not exist'):
        temp_repo.delete_tag('unexisting-tag')

def test_list_tags(temp_repo: Repository) -> None:
    temp_repo.working_dir.joinpath('f1').write_text('c1')
    c1 = temp_repo.commit_working_dir('A', 'M1')
    temp_repo.create_tag('v1.0', c1)

    temp_repo.working_dir.joinpath('f2').write_text('c2')
    c2 = temp_repo.commit_working_dir('A', 'M2')
    temp_repo.create_tag('v1.1', c2)
    temp_repo.create_tag('v1.2', c2)

    tag_list = temp_repo.tags()

    assert tag_list == ['v1.0', 'v1.1', 'v1.2']
    