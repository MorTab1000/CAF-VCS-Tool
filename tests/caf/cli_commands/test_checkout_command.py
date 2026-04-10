from libcaf.ref import SymRef
from libcaf.repository import AmbiguousRefError, Repository
from caf import cli_commands
from pytest import CaptureFixture

def test_checkout_short_branch_name_attaches_head(temp_repo: Repository) -> None:
    (temp_repo.working_dir / 'file.txt').write_text('base\n')
    temp_repo.commit_working_dir('QA', 'base')
    
    temp_repo.add_branch('feature')
    temp_repo.checkout('feature')
    
    head_file = temp_repo.working_dir / temp_repo.repo_dir / 'HEAD'
    head_content = head_file.read_text().strip()
    
    assert head_content == 'ref: heads/feature'
    
    (temp_repo.working_dir / 'file.txt').write_text('feature\n')
    temp_repo.commit_working_dir('QA', 'feature change')
    
    temp_repo.checkout('main')
    
    assert (temp_repo.working_dir / 'file.txt').read_text() == 'base\n'
    head_content = head_file.read_text().strip()
    assert head_content == 'ref: heads/main'


def test_cli_checkout_create_branch_flag(temp_repo: Repository) -> None:
    (temp_repo.working_dir / 'file.txt').write_text('base\n')
    temp_repo.commit_working_dir('QA', 'base')
    
    result = cli_commands.checkout(
        working_dir_path=str(temp_repo.working_dir),
        target_ref='my-feature',
        branch=True
    )
    
    assert result == 0
    assert temp_repo.branch_exists(SymRef('my-feature'))
    
    head_file = temp_repo.working_dir / temp_repo.repo_dir / 'HEAD'
    head_content = head_file.read_text().strip()
    assert head_content == 'ref: heads/my-feature'


def test_checkout_commit_hash_detaches_head(temp_repo: Repository) -> None:
    (temp_repo.working_dir / 'file.txt').write_text('v1\n')
    hash_v1 = temp_repo.commit_working_dir('QA', 'v1')
    
    (temp_repo.working_dir / 'file.txt').write_text('v2\n')
    temp_repo.commit_working_dir('QA', 'v2')
    
    temp_repo.checkout(hash_v1)
    
    assert (temp_repo.working_dir / 'file.txt').read_text() == 'v1\n'
    
    head_file = temp_repo.working_dir / temp_repo.repo_dir / 'HEAD'
    head_content = head_file.read_text().strip()
    assert head_content == hash_v1


def test_checkout_create_branch_on_empty_repo(temp_repo: Repository, capsys: CaptureFixture[str]) -> None:
    """Ensure checkout -b works on a brand new repository by swapping the unborn branch reservation."""
    result = cli_commands.checkout(working_dir_path=temp_repo.working_dir, target_ref='feature', branch=True)
    
    assert result == 0

    head_content = (temp_repo.working_dir / temp_repo.repo_path() / 'HEAD').read_text().strip()
    assert head_content == 'ref: heads/feature'

    assert "Switched to a new branch 'feature'" in capsys.readouterr().out


def test_integration_checkout_unborn_then_commit(temp_repo: Repository) -> None:
    """Swap unborn branch, then commit to prove the branch file is dynamically generated."""
    # Swap the unborn branch to 'feature'
    cli_commands.checkout(working_dir_path=temp_repo.working_dir, target_ref='feature', branch=True)
    
    # Create a file and make the very first commit
    (temp_repo.working_dir / 'test.txt').write_text('Hello World\n')
    commit_hash = temp_repo.commit_working_dir('Integration Tester', 'First commit on feature branch')
    
    # Verify the branch file was FINALLY born on disk
    feature_branch_file = temp_repo.working_dir / temp_repo.repo_path() / 'refs' / 'heads' / 'feature'
    assert feature_branch_file.exists(), "The commit command failed to birth the unborn branch!"
    assert feature_branch_file.read_text().strip() == commit_hash


def test_checkout_ambiguous_short_hash_prints_git_style_error(temp_repo: Repository, capsys: CaptureFixture[str]) -> None:
    short_hash = 'abcd'
    candidate_1 = 'abcd1234567890abcdef1234567890abcdef1234'
    candidate_2 = 'abcd9999567890abcdef1234567890abcdef1234'

    for commit_hash in [candidate_1, candidate_2]:
        commit_path = temp_repo.objects_dir() / commit_hash[:2] / commit_hash
        commit_path.parent.mkdir(parents=True, exist_ok=True)
        commit_path.write_text('dummy')

    result = cli_commands.checkout(
        working_dir_path=str(temp_repo.working_dir),
        target_ref=short_hash,
    )

    assert result == -1
    
    err_output = capsys.readouterr().err
    assert f"error: short hash '{short_hash}' is ambiguous" in err_output
    assert 'hint: The candidates are:' in err_output
    assert f'hint:   {candidate_1}' in err_output
    assert f'hint:   {candidate_2}' in err_output