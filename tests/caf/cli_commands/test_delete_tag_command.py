from pathlib import Path
from collections.abc import Callable
from libcaf.constants import DEFAULT_REPO_DIR, TAGS_DIR, REFS_DIR
from libcaf.repository import Repository
from pytest import CaptureFixture

from caf import cli_commands

def _create_initial_commit(repo: Repository, working_dir: Path, author: str, message: str, invoke_caf) -> None:
    """Helper to ensure the repository has a commit to tag."""
    (working_dir / 'initial_file.txt').write_text('content')
    invoke_caf(cli_commands.commit, repo, author=author, message=message)

def test_delete_tag_command(temp_repo: Repository, parse_commit_hash: Callable[[], str], capsys: CaptureFixture[str], invoke_caf) -> None:
    working_dir = temp_repo.working_dir
    _create_initial_commit(temp_repo, working_dir, 'Tag Author', 'Initial commit', invoke_caf)
    commit_hash = parse_commit_hash()
    tag_name = 'todelete'
    
    invoke_caf(cli_commands.create_tag, temp_repo, tag_name=tag_name, commit_hash=commit_hash)

    assert invoke_caf(cli_commands.delete_tag, temp_repo, tag_name=tag_name) == 0
    assert f'Tag "{tag_name}" deleted.' in capsys.readouterr().out

    tag_path = temp_repo.repo_path() / REFS_DIR / TAGS_DIR / tag_name
    assert not tag_path.exists()


def test_delete_tag_no_repo(temp_repo_dir: Path, capsys: CaptureFixture[str]) -> None:
    assert cli_commands.delete_tag(working_dir_path=temp_repo_dir, tag_name='feature') == -1
    assert 'No repository found' in capsys.readouterr().err


def test_delete_tag_missing_name(temp_repo: Repository, capsys: CaptureFixture[str], invoke_caf) -> None:
    assert invoke_caf(cli_commands.delete_tag, temp_repo, tag_name=None) == -1
    assert 'Tag name is required.' in capsys.readouterr().err


def test_delete_tag_does_not_exist(temp_repo: Repository, capsys: CaptureFixture[str], invoke_caf) -> None:
    assert invoke_caf(cli_commands.delete_tag, temp_repo, tag_name='nonexistent') == -1
    assert 'Tag "nonexistent" does not exist' in capsys.readouterr().err


def test_delete_tag_case_mismatch(temp_repo: Repository, parse_commit_hash: Callable[[], str], capsys: CaptureFixture[str], invoke_caf) -> None:
    working_dir = temp_repo.working_dir
    _create_initial_commit(temp_repo, working_dir, 'T', 'C', invoke_caf)
    commit_hash = parse_commit_hash()
    tag_name_upper = 'RELEASE_A'
    tag_name_lower = 'release_a'
    
    invoke_caf(cli_commands.create_tag, temp_repo, tag_name=tag_name_upper, commit_hash=commit_hash)
    tag_path = temp_repo.repo_path() / REFS_DIR / TAGS_DIR / tag_name_upper
    
    assert invoke_caf(cli_commands.delete_tag, temp_repo, tag_name=tag_name_lower) == -1
    assert f'Tag "{tag_name_lower}" does not exist' in capsys.readouterr().err
    
    assert tag_path.exists()