from collections.abc import Callable
from pathlib import Path

from libcaf import Commit
from libcaf.constants import DEFAULT_REPO_DIR, HEAD_FILE, SHORT_HASH_LENGTH
from libcaf.plumbing import hash_object, load_commit, save_commit
from libcaf.ref import HashRef
from libcaf.repository import Repository
from pytest import CaptureFixture

from caf import cli_commands


def test_log_command(temp_repo: Repository, parse_commit_hash: Callable[[], str], capsys: CaptureFixture[str], invoke_caf) -> None:
    working_dir = temp_repo.working_dir
    temp_file = working_dir / 'log_test.txt'
    temp_file.write_text('First commit content')

    assert invoke_caf(cli_commands.commit, temp_repo, message='First commit') == 0
    commit_hash1 = parse_commit_hash()

    temp_file.write_text('Second commit content')
    assert invoke_caf(cli_commands.commit, temp_repo, message='Second commit') == 0
    commit_hash2 = parse_commit_hash()

    assert invoke_caf(cli_commands.log, temp_repo) == 0

    output: str = capsys.readouterr().out
    assert commit_hash1[:SHORT_HASH_LENGTH] in output
    assert commit_hash2[:SHORT_HASH_LENGTH] in output
    assert 'TestBot' in output
    assert 'First commit' in output
    assert 'Second commit' in output


def test_log_no_repo(temp_repo_dir: Path, capsys: CaptureFixture[str]) -> None:
    assert cli_commands.log(working_dir_path=temp_repo_dir) == -1
    assert 'No repository found' in capsys.readouterr().err


def test_log_repo_error(temp_repo: Repository, capsys: CaptureFixture[str], invoke_caf) -> None:
    working_dir = temp_repo.working_dir
    (working_dir / DEFAULT_REPO_DIR / HEAD_FILE).unlink()
    assert invoke_caf(cli_commands.log, temp_repo) == -1

    assert 'Repository error' in capsys.readouterr().err


def test_log_no_commits(temp_repo: Repository, capsys: CaptureFixture[str], invoke_caf) -> None:
    assert invoke_caf(cli_commands.log, temp_repo) == 0
    assert 'No commits in the repository' in capsys.readouterr().out


def test_log_prints_merge_indicator_with_short_parent_hashes(temp_repo: Repository,
                                                             capsys: CaptureFixture[str], invoke_caf) -> None:
    working_dir = temp_repo.working_dir
    temp_file = working_dir / 'merge_log_test.txt'
    temp_file.write_text('base')

    base_ref = temp_repo.commit_working_dir('Log Tester', 'base commit')
    base_commit = load_commit(temp_repo.objects_dir(), base_ref)
    base_ts = base_commit.timestamp

    left_commit = Commit(base_commit.tree_hash, 'Log Tester', 'left', base_ts + 2, [base_ref])
    save_commit(temp_repo.objects_dir(), left_commit)
    left_ref = hash_object(left_commit)

    right_commit = Commit(base_commit.tree_hash, 'Log Tester', 'right', base_ts + 3, [base_ref])
    save_commit(temp_repo.objects_dir(), right_commit)
    right_ref = hash_object(right_commit)

    merge_commit = Commit(base_commit.tree_hash, 'Log Tester', 'merge', base_ts + 4, [left_ref, right_ref])
    save_commit(temp_repo.objects_dir(), merge_commit)
    merge_ref = hash_object(merge_commit)

    temp_repo.update_head(HashRef(merge_ref))

    assert invoke_caf(cli_commands.log, temp_repo) == 0

    output = capsys.readouterr().out
    assert f'Commit: {merge_ref[:SHORT_HASH_LENGTH]}' in output
    assert f'Merge: {left_ref[:SHORT_HASH_LENGTH]} {right_ref[:SHORT_HASH_LENGTH]}' in output
