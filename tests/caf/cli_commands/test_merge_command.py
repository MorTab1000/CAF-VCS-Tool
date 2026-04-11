import shutil

import pytest
from libcaf.plumbing import load_commit
from libcaf.repository import Repository
from pytest import CaptureFixture
from libcaf.ref import SymRef, HashRef
from caf import cli_commands
from libcaf.constants import SHORT_HASH_LENGTH


def _set_working_tree_files(temp_repo: Repository, files: dict[str, str]) -> None:
    """Replace working tree files (excluding .caf) with a deterministic snapshot."""
    for item in temp_repo.working_dir.iterdir():
        if item.name == temp_repo.repo_dir.name:
            continue

        if item.is_dir():
            shutil.rmtree(item)
        else:
            item.unlink()

    for rel_path, content in files.items():
        file_path = temp_repo.working_dir / rel_path
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(content)


def _setup_text_conflict_state(temp_repo: Repository) -> tuple[str, str]:
    """Create an unresolved text conflict on main and materialize MERGE_HEAD on disk."""
    _set_working_tree_files(temp_repo, {'conflict.txt': 'base\n'})
    base_hash = temp_repo.commit_working_dir('QA', 'base')

    temp_repo.add_branch('feature')
    temp_repo.update_ref('heads/feature', base_hash)

    # Move HEAD to main and create ours
    temp_repo.update_head(SymRef('heads/main'))
    _set_working_tree_files(temp_repo, {'conflict.txt': 'ours\n'})
    ours_hash = temp_repo.commit_working_dir('QA', 'main change')

    # Move HEAD to feature and create theirs
    temp_repo.update_head(SymRef('heads/feature'))
    _set_working_tree_files(temp_repo, {'conflict.txt': 'theirs\n'})
    theirs_hash = temp_repo.commit_working_dir('QA', 'feature change')

    temp_repo.checkout(SymRef('heads/main'))
    
    report = temp_repo.merge(temp_repo.head_ref(), SymRef('heads/feature'), 'QA') 
    
    temp_repo.apply_conflicts_to_disk(report.conflicts, theirs_hash)

    return ours_hash, theirs_hash


def test_merge_missing_target_argument_aborts_with_error(temp_repo: Repository, capsys: CaptureFixture[str]) -> None:
    result = cli_commands.merge(working_dir_path=str(temp_repo.working_dir), target_ref=None, author='QA')
    
    assert result == -1
    err = capsys.readouterr().err.lower()
    assert 'error' in err
    assert 'required' in err


def test_merge_invalid_reference_aborts_gracefully(temp_repo: Repository, capsys: CaptureFixture[str]) -> None:
    (temp_repo.working_dir / 'seed.txt').write_text('seed\n')
    temp_repo.commit_working_dir('QA', 'seed commit')

    result = cli_commands.merge(working_dir_path=str(temp_repo.working_dir), target_ref='nonexistent-branch', author='QA')

    assert result == -1
    err = capsys.readouterr().err.lower()
    assert 'error' in err
    assert 'nonexistent-branch' in err or 'not found' in err


def test_merge_clean_merge_outputs_hash_and_updates_workspace(temp_repo: Repository, capsys: CaptureFixture[str]) -> None:
    _set_working_tree_files(temp_repo, {'file_a.txt': 'base a\n', 'file_b.txt': 'base b\n'})
    base_hash = temp_repo.commit_working_dir('QA', 'base')

    temp_repo.add_branch('feature')
    temp_repo.update_ref('heads/feature', base_hash)

    temp_repo.update_head(SymRef('heads/main'))
    _set_working_tree_files(temp_repo, {'file_a.txt': 'main changed a\n', 'file_b.txt': 'base b\n'})
    temp_repo.commit_working_dir('QA', 'main changes a')

    temp_repo.update_head(SymRef('heads/feature'))
    _set_working_tree_files(temp_repo, {'file_a.txt': 'base a\n', 'file_b.txt': 'feature changed b\n'})
    temp_repo.commit_working_dir('QA', 'feature changes b')

    temp_repo.checkout(SymRef('heads/main'))

    result = cli_commands.merge(
        working_dir_path=str(temp_repo.working_dir),
        target_ref='feature',
        author='QA'
    )

    assert result == 0
    head_hash = temp_repo.head_commit()
    
    assert head_hash is not None
    assert (temp_repo.working_dir / 'file_a.txt').read_text() == 'main changed a\n'
    assert (temp_repo.working_dir / 'file_b.txt').read_text() == 'feature changed b\n'


def test_merge_content_conflict_writes_merge_head(temp_repo: Repository, capsys: CaptureFixture[str]) -> None:
    _set_working_tree_files(temp_repo, {'conflict.txt': 'base\n'})
    base_hash = temp_repo.commit_working_dir('QA', 'base')

    temp_repo.add_branch('feature')
    temp_repo.update_ref('heads/feature', base_hash)

    temp_repo.update_head(SymRef('heads/main'))
    _set_working_tree_files(temp_repo, {'conflict.txt': 'ours\n'})
    temp_repo.commit_working_dir('QA', 'main change')

    temp_repo.update_head(SymRef('heads/feature'))
    _set_working_tree_files(temp_repo, {'conflict.txt': 'theirs\n'})
    source_hash = temp_repo.commit_working_dir('QA', 'feature change')

    temp_repo.checkout(SymRef('heads/main'))

    result = cli_commands.merge(working_dir_path=str(temp_repo.working_dir), target_ref='feature', author='QA')

    assert result == -1 
    
    output = capsys.readouterr().out.lower() 
    assert 'conflict' in output

    merge_head = temp_repo.merge_head_file()
    assert merge_head.exists()
    assert merge_head.read_text().strip() == str(source_hash)


def test_commit_blocked_when_unresolved_conflict_markers_exist(temp_repo: Repository, capsys: CaptureFixture[str]) -> None:
    old_head, _ = _setup_text_conflict_state(temp_repo)
    conflicted_file = temp_repo.working_dir / 'conflict.txt'
    
    assert b'<<<<<<< HEAD' in conflicted_file.read_bytes()

    result = cli_commands.commit(
        working_dir_path=str(temp_repo.working_dir), 
        author='QA', 
        message='attempt merge commit'
    )

    assert result == -1
    err = capsys.readouterr().err.lower()
    assert 'cannot commit' in err or 'unresolved' in err
    assert temp_repo.head_commit() == old_head


def test_commit_after_resolving_conflicts_creates_two_parent_commit(temp_repo: Repository) -> None:
    old_head, theirs_hash = _setup_text_conflict_state(temp_repo)
    merge_head_file = temp_repo.merge_head_file()
    assert merge_head_file.exists()

    # User resolves the file
    (temp_repo.working_dir / 'conflict.txt').write_text('resolved final content\n')

    result = cli_commands.commit(
        working_dir_path=str(temp_repo.working_dir), 
        author='QA', 
        message='resolve merge conflict'
    )

    assert result == 0
    new_head = temp_repo.head_commit()
    assert new_head is not None
    assert new_head != old_head
    
    new_commit = load_commit(temp_repo.objects_dir(), new_head)
    
    assert len(new_commit.parents) == 2
    assert set(new_commit.parents) == {old_head, theirs_hash}
    assert not merge_head_file.exists()


def test_merge_with_commit_hash_succeeds(temp_repo: Repository, capsys: CaptureFixture[str]) -> None:
    _set_working_tree_files(temp_repo, {'file_a.txt': 'base\n'})
    base_hash = temp_repo.commit_working_dir('QA', 'base')

    # Setup feature branch with a new commit
    temp_repo.add_branch('feature')
    temp_repo.update_ref('heads/feature', base_hash)
    temp_repo.update_head(SymRef('heads/feature'))
    _set_working_tree_files(temp_repo, {'file_a.txt': 'feature change\n'})
    
    # Capture the raw 40-character commit hash
    feature_hash = temp_repo.commit_working_dir('QA', 'feature change')

    temp_repo.checkout(SymRef('heads/main'))

    result = cli_commands.merge(
        working_dir_path=str(temp_repo.working_dir),
        target_ref=str(feature_hash), 
        author='QA'
    )

    assert result == 0
    assert 'fast-forward' in capsys.readouterr().out.lower()


def test_merge_with_tag_succeeds(temp_repo: Repository, capsys: CaptureFixture[str]) -> None:
    _set_working_tree_files(temp_repo, {'file_a.txt': 'base\n'})
    base_hash = temp_repo.commit_working_dir('QA', 'base')

    # Setup feature branch with a new commit
    temp_repo.add_branch('feature')
    temp_repo.update_ref('heads/feature', base_hash)
    temp_repo.update_head(SymRef('heads/feature'))
    _set_working_tree_files(temp_repo, {'file_a.txt': 'feature change\n'})
    feature_hash = temp_repo.commit_working_dir('QA', 'feature change')

    # Create a tag pointing to the feature commit
    temp_repo.create_tag('v1.0', feature_hash)

    # Go back to main
    temp_repo.checkout(SymRef('heads/main'))

    result = cli_commands.merge(
        working_dir_path=str(temp_repo.working_dir),
        target_ref='v1.0', 
        author='QA'
    )

    assert result == 0
    assert 'fast-forward' in capsys.readouterr().out.lower()


def test_merge_in_detached_head_fast_forwards_correctly(temp_repo: Repository, capsys: CaptureFixture[str]) -> None:
    _set_working_tree_files(temp_repo, {'file_a.txt': 'base\n'})
    base_hash = temp_repo.commit_working_dir('QA', 'base')

    # Setup feature branch with a new commit
    temp_repo.add_branch('feature')
    temp_repo.update_ref('heads/feature', base_hash)
    temp_repo.update_head(SymRef('heads/feature'))
    _set_working_tree_files(temp_repo, {'file_a.txt': 'feature change\n'})
    feature_hash = temp_repo.commit_working_dir('QA', 'feature change')

    # Force a Detached HEAD state by checking out the raw base commit hash
    temp_repo.checkout(HashRef(base_hash))
    
    # Verify we are actually detached before we start
    assert isinstance(temp_repo.head_ref(), HashRef)

    # Merge the feature branch into our detached HEAD
    result = cli_commands.merge(
        working_dir_path=str(temp_repo.working_dir),
        target_ref='feature',
        author='QA'
    )

    assert result == 0

    # CLI output confirms fast-forward
    output = capsys.readouterr().out.lower()
    assert 'fast-forward' in output

    # HEAD is STILL detached (HashRef), but has stepped forward to the new commit
    current_head = temp_repo.head_ref()
    assert isinstance(current_head, HashRef)
    assert str(current_head) == str(feature_hash)
    
    # Physical files updated correctly
    assert (temp_repo.working_dir / 'file_a.txt').read_text() == 'feature change\n'


def test_merge_with_conflicts_and_clean_updates_saves_clean_files(temp_repo: Repository, capsys: CaptureFixture[str]) -> None:
    """
    Simulates a realistic merge where some files auto-merge/clean-update, and others conflict.
    Verifies that clean updates are NOT lost when the CLI halts for conflict resolution.
    """
    # Setup Base
    _set_working_tree_files(temp_repo, {
        'clean.txt': 'base clean\n',
        'conflict.txt': 'base conflict\n'
    })
    base_hash = temp_repo.commit_working_dir('QA', 'base')

    # Setup Feature Branch
    temp_repo.add_branch('feature')
    temp_repo.update_ref('heads/feature', base_hash)
    temp_repo.update_head(SymRef('heads/feature'))
    _set_working_tree_files(temp_repo, {
        'clean.txt': 'feature clean\n',      # Clean update
        'conflict.txt': 'feature conflict\n' # Will cause conflict
    })
    _ = temp_repo.commit_working_dir('QA', 'feature change')

    # Setup Main Branch
    temp_repo.checkout(SymRef('heads/main'))
    _set_working_tree_files(temp_repo, {
        'conflict.txt': 'main conflict\n'    # Causes the conflict
    })
    temp_repo.commit_working_dir('QA', 'main change')

    result = cli_commands.merge(
        working_dir_path=str(temp_repo.working_dir),
        target_ref='feature',
        author='QA'
    )

    # Verify CLI stopped for conflict
    assert result == -1

    assert (temp_repo.working_dir / 'clean.txt').read_text() == 'feature clean\n'

    # The conflict markers were written
    conflict_content = (temp_repo.working_dir / 'conflict.txt').read_text()
    assert '<<<<<<< HEAD' in conflict_content

    # Resolve the conflict and test the Gatekeeper boundary
    _set_working_tree_files(temp_repo, {
        'conflict.txt': 'resolved conflict\n'
    })

    backup_file = temp_repo.working_dir / 'conflict.txt~MERGE_HEAD'
    if backup_file.exists():
        backup_file.unlink()

    # Prove the gatekeeper allows the commit to proceed without throwing an error
    try:
        temp_repo.commit_working_dir('QA', 'Merge resolved')
    except Exception as e:
        pytest.fail(f"Gatekeeper incorrectly blocked the commit after resolution! Error: {e}")


def test_merge_cli_abort_success(temp_repo: Repository, capsys: CaptureFixture[str]) -> None:
    (temp_repo.working_dir / 'init.txt').write_text('init\n')
    temp_repo.commit_working_dir('Author', 'Base commit')

    merge_head = temp_repo.merge_head_file()
    merge_head.write_text(temp_repo.head_commit())

    result = cli_commands.merge(
        working_dir_path=str(temp_repo.working_dir),
        abort=True,
    )

    assert result == 0
    captured = capsys.readouterr()
    assert 'Merge aborted successfully' in captured.out


def test_merge_cli_abort_fails_clean_repo(temp_repo: Repository, capsys: CaptureFixture[str]) -> None:
    result = cli_commands.merge(
        working_dir_path=str(temp_repo.working_dir),
        abort=True,
    )

    assert result == -1
    captured = capsys.readouterr()
    assert 'No merge in progress' in (captured.out + captured.err)


def test_cli_merge_resolves_branches_and_short_hashes(temp_repo: Repository) -> None:
    # 1. Base Commit
    (temp_repo.working_dir / 'base.txt').write_text('Base Line')
    base_hash = temp_repo.commit_working_dir('Mor', 'Base commit')
    
    # 2. Feature Branch
    temp_repo.add_branch('feature')
    temp_repo.checkout('heads/feature')
    (temp_repo.working_dir / 'feature.txt').write_text('Feature Line')
    temp_repo.commit_working_dir('Mor', 'Feature commit')
    
    # 3. Main Branch
    temp_repo.checkout('heads/main')
    (temp_repo.working_dir / 'main.txt').write_text('Main Line')
    main_hash = temp_repo.commit_working_dir('Mor', 'Main commit')
    
    # 4. Detached Short Hash Target
    temp_repo.checkout(base_hash)
    (temp_repo.working_dir / 'raw.txt').write_text('Raw Line')
    raw_hash = temp_repo.commit_working_dir('Mor', 'Raw commit')
    
    # CRITICAL TEST FIX: Force it to be a pure string to mimic CLI typing!
    short_hash = str(raw_hash)[:SHORT_HASH_LENGTH] 
    
    # --- Execute Branch Merge ---
    temp_repo.checkout('heads/main')
    result_code_branch = cli_commands.merge(working_dir_path=temp_repo.working_dir, repo_dir=temp_repo.repo_dir, target_ref='feature', author='Mor')
    assert result_code_branch == 0
    
    # --- Execute Short Hash Merge ---
    temp_repo.checkout(main_hash)
    result_code_hash = cli_commands.merge(working_dir_path=temp_repo.working_dir, repo_dir=temp_repo.repo_dir, target_ref=short_hash, author='Mor')
    assert result_code_hash == 0