from pathlib import Path

from libcaf.constants import DEFAULT_REPO_DIR, HEADS_DIR, REFS_DIR
from libcaf.repository import Repository
from pytest import CaptureFixture

from caf import cli_commands


def test_add_branch_command(temp_repo: Repository) -> None:
    temp_repo.commit_working_dir('Test Author', 'Initial commit')
    assert cli_commands.add_branch(working_dir_path=temp_repo.working_dir, branch_name='feature') == 0

    branch_path = temp_repo.working_dir / DEFAULT_REPO_DIR / REFS_DIR / HEADS_DIR / 'feature'
    assert branch_path.exists()


def test_add_branch_missing_name(temp_repo: Repository, capsys: CaptureFixture[str]) -> None:
    assert cli_commands.add_branch(working_dir_path=temp_repo.working_dir) == -1
    assert 'Branch name is required' in capsys.readouterr().err


def test_add_branch_twice(temp_repo: Repository, capsys: CaptureFixture[str]) -> None:
    temp_repo.commit_working_dir('Test Author', 'Initial commit')
    assert cli_commands.add_branch(working_dir_path=temp_repo.working_dir, branch_name='feature') == 0
    assert cli_commands.add_branch(working_dir_path=temp_repo.working_dir, branch_name='feature') == -1

    assert 'Branch "feature" already exists' in capsys.readouterr().err


def test_add_branch_no_repo(temp_repo_dir: Path, capsys: CaptureFixture[str]) -> None:
    assert cli_commands.add_branch(working_dir_path=temp_repo_dir, branch_name='feature') == -1
    assert 'No repository found at' in capsys.readouterr().err


def test_cli_add_branch_empty_repo_returns_error(temp_repo: Repository, capsys: CaptureFixture[str]) -> None:
    """Ensure the CLI gracefully handles adding a branch before the first commit."""
    result = cli_commands.add_branch(working_dir_path=temp_repo.working_dir, branch_name='feature')
    
    assert result == -1
    
    stderr = capsys.readouterr().err
    assert "Cannot create branch 'feature'" in stderr
    assert "You must make your first commit" in stderr
