from libcaf.constants import DEFAULT_BRANCH, SHORT_HASH_LENGTH
from libcaf.repository import Repository
from pytest import CaptureFixture

from caf import cli_commands

def test_status_on_unborn_branch_reports_clean_tree(temp_repo: Repository, capsys: CaptureFixture[str]) -> None:
    assert cli_commands.status(working_dir_path=temp_repo.working_dir) == 0

    output = capsys.readouterr().out
    assert f'On branch {DEFAULT_BRANCH}' in output
    assert 'nothing to commit, working tree clean' in output
    assert 'No commits yet' in output


def test_status_on_clean_working_tree_after_commit(temp_repo: Repository, capsys: CaptureFixture[str]) -> None:
    tracked_file = temp_repo.working_dir / 'tracked.txt'
    tracked_file.write_text('tracked content\n')

    temp_repo.commit_working_dir('Status Tester', 'Initial commit')
    capsys.readouterr()

    assert cli_commands.status(working_dir_path=temp_repo.working_dir) == 0

    output = capsys.readouterr().out
    assert f'On branch {DEFAULT_BRANCH}' in output
    assert 'nothing to commit, working tree clean' in output


def test_status_reports_added_modified_and_deleted_files(temp_repo: Repository,
                                                        capsys: CaptureFixture[str]) -> None:
    to_modify = temp_repo.working_dir / 'to_modify.txt'
    to_delete = temp_repo.working_dir / 'to_delete.txt'
    untouched = temp_repo.working_dir / 'untouched.txt'

    to_modify.write_text('before\n')
    to_delete.write_text('delete me\n')
    untouched.write_text('same\n')

    temp_repo.commit_working_dir('Status Tester', 'Track baseline files')

    to_modify.write_text('after\n')
    to_delete.unlink()
    (temp_repo.working_dir / 'added.txt').write_text('new file\n')

    capsys.readouterr()

    assert cli_commands.status(working_dir_path=temp_repo.working_dir) == 0

    output = capsys.readouterr().out
    assert 'Uncommitted changes in working directory:' in output
    assert 'new file: added.txt' in output
    assert 'modified: to_modify.txt' in output
    assert 'deleted: to_delete.txt' in output
    assert 'untouched.txt' not in output


def test_status_reports_detached_head(temp_repo: Repository, capsys: CaptureFixture[str]) -> None:
    (temp_repo.working_dir / 'dummy.txt').write_text('content\n')
    head_hash = temp_repo.commit_working_dir('Status Tester', 'Initial commit')
    
    temp_repo.update_head(head_hash)
    
    # Clear the capture buffer before running our command
    capsys.readouterr()
    
    assert cli_commands.status(working_dir_path=temp_repo.working_dir) == 0
    
    # Verify the exact detached output
    output = capsys.readouterr().out
    short_hash = head_hash[:SHORT_HASH_LENGTH]
    
    assert f'HEAD detached at {short_hash}' in output
    assert 'nothing to commit, working tree clean' in output
