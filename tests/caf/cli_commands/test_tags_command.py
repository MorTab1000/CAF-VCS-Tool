from collections.abc import Callable
from pathlib import Path
from collections.abc import Callable
from libcaf.constants import DEFAULT_REPO_DIR, TAGS_DIR, REFS_DIR
from libcaf.repository import Repository
from pytest import CaptureFixture

from caf import cli_commands

def _create_initial_commit(repo: Repository, working_dir: Path, author: str, message: str, invoke_caf: Callable[..., int]) -> None:
    """Helper to ensure the repository has a commit to tag."""
    (working_dir / 'initial_file.txt').write_text('content')
    invoke_caf(cli_commands.commit, repo, author=author, message=message)

def test_tags_command_list(temp_repo: Repository, parse_commit_hash: Callable[[], str], capsys: CaptureFixture[str], invoke_caf: Callable[..., int]) -> None:
    working_dir = temp_repo.working_dir
    _create_initial_commit(temp_repo, working_dir, 'Tag Author', 'Initial commit', invoke_caf)
    commit_hash = parse_commit_hash()

    invoke_caf(cli_commands.create_tag, temp_repo, tag_name='beta', commit_hash=commit_hash)
    invoke_caf(cli_commands.create_tag, temp_repo, tag_name='alpha', commit_hash=commit_hash)
    
    capsys.readouterr() # Clear the buffer

    assert invoke_caf(cli_commands.tags, temp_repo) == 0

    output = capsys.readouterr().out
    assert 'Tags:' in output
    
    lines = output.splitlines()
    tag_lines = [line.strip() for line in lines if line.strip() and not line.strip().startswith('Tags:')]
    
    assert tag_lines == ['alpha', 'beta'], "Tags should be listed in alphabetical order"


def test_tags_case_sensitivity(temp_repo: Repository, parse_commit_hash: Callable[[], str], capsys: CaptureFixture[str], invoke_caf: Callable[..., int]) -> None:
    working_dir = temp_repo.working_dir
    _create_initial_commit(temp_repo, working_dir, 'T', 'C', invoke_caf)
    commit_hash = parse_commit_hash()

    invoke_caf(cli_commands.create_tag, temp_repo, tag_name='TagA', commit_hash=commit_hash)
    invoke_caf(cli_commands.create_tag, temp_repo, tag_name='taga', commit_hash=commit_hash)
    
    capsys.readouterr() 

    assert invoke_caf(cli_commands.tags, temp_repo) == 0
    output = capsys.readouterr().out
    
    lines = output.splitlines()
    tag_lines = [line.strip() for line in lines if line.strip() and not line.strip().startswith('Tags:')]
    
    assert tag_lines == ['TagA', 'taga'], "Case-sensitive tags should be sorted correctly"


def test_tags_no_repo(temp_repo_dir: Path, capsys: CaptureFixture[str]) -> None:
    assert cli_commands.tags(working_dir_path=temp_repo_dir) == -1
    assert 'No repository found' in capsys.readouterr().err


def test_tags_no_tags_exist(temp_repo: Repository, capsys: CaptureFixture[str], invoke_caf: Callable[..., int]) -> None:
    assert invoke_caf(cli_commands.tags, temp_repo) == 0
    assert 'No tags found.' in capsys.readouterr().out
