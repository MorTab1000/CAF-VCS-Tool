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

