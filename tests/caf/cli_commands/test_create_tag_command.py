from pathlib import Path
from collections.abc import Callable
from libcaf.constants import DEFAULT_REPO_DIR, TAGS_DIR, REFS_DIR
from libcaf.repository import Repository
from pytest import CaptureFixture

from caf import cli_commands

def _create_initial_commit(repo: Repository, working_dir: Path, author: str, message: str) -> None:
    """Helper to ensure the repository has a commit to tag."""
    (working_dir / 'initial_file.txt').write_text('content')
    cli_commands.commit(working_dir_path=working_dir, author=author, message=message)

def test_create_tag_command(temp_repo: Repository, parse_commit_hash: Callable[[], str], capsys: CaptureFixture[str]) -> None:
    working_dir = temp_repo.working_dir
    _create_initial_commit(temp_repo, working_dir, 'Tag Author', 'Initial commit for tag')
    commit_hash = parse_commit_hash()
    tag_name = 'v1.0.0'

    assert cli_commands.create_tag(working_dir_path=working_dir, tag_name=tag_name, commit_hash=commit_hash) == 0

    output = capsys.readouterr().out
    assert f'Tag "{tag_name}" created for commit {commit_hash}.' in output

    tag_path = temp_repo.repo_path() / REFS_DIR / TAGS_DIR / tag_name
    assert tag_path.exists()
    assert tag_path.read_text().strip() == commit_hash


def test_create_tag_no_repo(temp_repo_dir: Path, capsys: CaptureFixture[str]) -> None:
    assert cli_commands.create_tag(working_dir_path=temp_repo_dir, tag_name='test', commit_hash='fake_hash') == -1
    assert 'No repository found' in capsys.readouterr().err


def test_create_tag_missing_arguments(temp_repo: Repository, capsys: CaptureFixture[str]) -> None:
    assert cli_commands.create_tag(working_dir_path=temp_repo.working_dir, tag_name=None, commit_hash='fake_hash') == -1
    assert 'Tag name is required.' in capsys.readouterr().err
    
    assert cli_commands.create_tag(working_dir_path=temp_repo.working_dir, tag_name='test', commit_hash=None) == -1
    assert 'Commit hash is required.' in capsys.readouterr().err


def test_create_tag_already_exists(temp_repo: Repository, parse_commit_hash: Callable[[], str], capsys: CaptureFixture[str]) -> None:
    working_dir = temp_repo.working_dir
    _create_initial_commit(temp_repo, working_dir, 'Tag Author', 'Initial commit')
    commit_hash = parse_commit_hash()
    tag_name = 'v1.0.0'

    cli_commands.create_tag(working_dir_path=working_dir, tag_name=tag_name, commit_hash=commit_hash)

    assert cli_commands.create_tag(working_dir_path=working_dir, tag_name=tag_name, commit_hash=commit_hash) == -1
    assert 'Repository error: Tag "v1.0.0" already exists' in capsys.readouterr().err


def test_create_tag_invalid_commit_hash(temp_repo: Repository, capsys: CaptureFixture[str]) -> None:
    assert cli_commands.create_tag(working_dir_path=temp_repo.working_dir, tag_name='test', commit_hash='fake_hash') == -1
    assert 'Repository error: Invalid commit reference: Invalid reference: fake_hash' in capsys.readouterr().err


def test_create_tag_on_empty_repo_history(temp_repo: Repository, capsys: CaptureFixture[str]) -> None:
    assert cli_commands.create_tag(working_dir_path=temp_repo.working_dir, 
                                   tag_name='first_tag', 
                                   commit_hash='fake_hash') == -1
    
    assert 'Repository error: Invalid commit reference: Invalid reference: fake_hash' in capsys.readouterr().err
