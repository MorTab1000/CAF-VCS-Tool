from libcaf.repository import Repository, RepositoryError
from pytest import raises


def test_checkout_additions_writes_new_files_to_disk(temp_repo: Repository) -> None:
    base_file = temp_repo.working_dir / 'base.txt'
    base_file.write_text('base content')
    commit_ref1 = temp_repo.commit_working_dir('Author', 'Base commit')

    new_file = temp_repo.working_dir / 'new_file.txt'
    nested_dir = temp_repo.working_dir / 'docs'
    nested_file = nested_dir / 'notes.txt'

    nested_dir.mkdir()
    new_file.write_text('new file content')
    nested_file.write_text('nested file content')
    commit_ref2 = temp_repo.commit_working_dir('Author', 'Add new files')

    temp_repo.checkout(commit_ref1)
    assert not new_file.exists()
    assert not nested_file.exists()

    temp_repo.checkout(commit_ref2)

    assert new_file.exists()
    assert nested_file.exists()
    assert new_file.read_text() == 'new file content'
    assert nested_file.read_text() == 'nested file content'


def test_checkout_deletions_unlinks_files_on_disk(temp_repo: Repository) -> None:
    stable_file = temp_repo.working_dir / 'stable.txt'
    stable_file.write_text('always present')
    commit_ref1 = temp_repo.commit_working_dir('Author', 'Initial state')

    later_file = temp_repo.working_dir / 'later.txt'
    later_file.write_text('introduced later')

    temp_repo.commit_working_dir('Author', 'Add later file')

    temp_repo.checkout(commit_ref1)

    assert stable_file.exists()
    assert not later_file.exists()


def test_checkout_modifications_updates_file_content(temp_repo: Repository) -> None:
    target_file = temp_repo.working_dir / 'config.ini'
    target_file.write_text('version=1')
    commit_ref1 = temp_repo.commit_working_dir('Author', 'Initial config')

    target_file.write_text('version=2')
    commit_ref2 = temp_repo.commit_working_dir('Author', 'Update config')

    temp_repo.checkout(commit_ref1)
    assert target_file.read_text() == 'version=1'

    temp_repo.checkout(commit_ref2)
    assert target_file.read_text() == 'version=2'


def test_checkout_updates_head_to_target_ref(temp_repo: Repository) -> None:
    file_path = temp_repo.working_dir / 'head_state.txt'
    file_path.write_text('first')
    commit_ref1 = temp_repo.commit_working_dir('Author', 'First commit')

    file_path.write_text('second')
    commit_ref2 = temp_repo.commit_working_dir('Author', 'Second commit')

    assert temp_repo.head_commit() == commit_ref2

    temp_repo.checkout(commit_ref1)

    assert temp_repo.head_commit() == commit_ref1


def test_checkout_dirty_workspace_conflict_raises_and_aborts(temp_repo: Repository) -> None: 
    tracked_file = temp_repo.working_dir / 'tracked.txt'
    tracked_file.write_text('base')
    commit_ref1 = temp_repo.commit_working_dir('Author', 'Base commit')

    tracked_file.write_text('target version')
    commit_ref2 = temp_repo.commit_working_dir('Author', 'Target commit')

    temp_repo.checkout(commit_ref1)
    assert tracked_file.read_text() == 'base'

    dirty_content = 'dirty local change'
    tracked_file.write_text(dirty_content)

    with raises(RepositoryError):
        temp_repo.checkout(commit_ref2)

    # Checkout must abort without changing disk state or HEAD.
    assert tracked_file.read_text() == dirty_content
    assert temp_repo.head_ref() == commit_ref1


def test_checkout_renames_file_correctly(temp_repo: Repository) -> None:
    old_path = temp_repo.working_dir / 'old_name.txt'
    old_content = 'same content after move'
    old_path.write_text(old_content)
    commit_ref1 = temp_repo.commit_working_dir('Author', 'Initial file location')

    new_dir = temp_repo.working_dir / 'renamed_dir'
    new_path = new_dir / 'new_name.txt'
    new_dir.mkdir()
    old_path.rename(new_path)
    commit_ref2 = temp_repo.commit_working_dir('Author', 'Move file to a new directory')

    temp_repo.checkout(commit_ref1)
    assert old_path.exists()
    assert not new_path.exists()
    assert temp_repo.head_ref() == commit_ref1

    temp_repo.checkout(commit_ref2)
    assert not old_path.exists()
    assert new_path.exists()
    assert new_path.read_text() == old_content
    assert temp_repo.head_ref() == commit_ref2


def test_checkout_removes_empty_directories(temp_repo: Repository) -> None:
    keep_file = temp_repo.working_dir / 'keep.txt'
    keep_file.write_text('persist across commits')
    commit_ref1 = temp_repo.commit_working_dir('Author', 'Base without temp directory')

    ephemeral_dir = temp_repo.working_dir / 'ephemeral'
    ephemeral_file = ephemeral_dir / 'only_file.txt'
    ephemeral_dir.mkdir()
    ephemeral_file.write_text('temporary content')
    commit_ref2 = temp_repo.commit_working_dir('Author', 'Add temporary directory and file')

    temp_repo.checkout(commit_ref1)
    assert not ephemeral_file.exists()
    assert not ephemeral_dir.exists()
    assert keep_file.exists()

    temp_repo.checkout(commit_ref2)
    assert ephemeral_file.exists()
    assert ephemeral_dir.exists()


def test_checkout_ignores_untracked_files(temp_repo: Repository) -> None:
    tracked_file = temp_repo.working_dir / 'tracked.txt'
    tracked_file.write_text('v1')
    commit_ref1 = temp_repo.commit_working_dir('Author', 'Track file v1')

    tracked_file.write_text('v2')
    commit_ref2 = temp_repo.commit_working_dir('Author', 'Track file v2')

    untracked_file = temp_repo.working_dir / 'untracked.local'
    untracked_content = 'do not modify me'
    untracked_file.write_text(untracked_content)

    temp_repo.checkout(commit_ref1)

    assert tracked_file.read_text() == 'v1'
    assert untracked_file.exists()
    assert untracked_file.read_text() == untracked_content

    temp_repo.checkout(commit_ref2)
    assert tracked_file.read_text() == 'v2'
    assert untracked_file.exists()
    assert untracked_file.read_text() == untracked_content


def test_checkout_aborts_when_untracked_file_in_the_way_of_addition(temp_repo: Repository) -> None:
    base_file = temp_repo.working_dir / 'base.txt'
    base_file.write_text('base')
    commit_ref1 = temp_repo.commit_working_dir('Author', 'Base commit')

    incoming_file = temp_repo.working_dir / 'important_config.json'
    incoming_file.write_text('tracked config data')
    commit_ref2 = temp_repo.commit_working_dir('Author', 'Add incoming config')

    temp_repo.checkout(commit_ref1)
    assert not incoming_file.exists()

    untracked_content = 'my secret local api keys'
    incoming_file.write_text(untracked_content)

    with raises(RepositoryError):
        temp_repo.checkout(commit_ref2)

    assert incoming_file.read_text() == untracked_content
    assert temp_repo.head_commit() == commit_ref1


def test_checkout_handles_chained_renames_safely(temp_repo: Repository) -> None:
    file_a = temp_repo.working_dir / 'a.txt'
    file_b = temp_repo.working_dir / 'b.txt'
    file_a.write_text('content A')
    file_b.write_text('content B')
    commit_ref1 = temp_repo.commit_working_dir('Author', 'Base commit')

    file_c = temp_repo.working_dir / 'c.txt'
    file_b.rename(file_c)
    file_a.rename(file_b) 
    commit_ref2 = temp_repo.commit_working_dir('Author', 'Chained rename')

    temp_repo.checkout(commit_ref1)
    assert file_a.exists() and file_a.read_text() == 'content A'
    assert file_b.exists() and file_b.read_text() == 'content B'
    assert not file_c.exists()

    temp_repo.checkout(commit_ref2)

    assert not file_a.exists()
    assert file_b.exists() and file_b.read_text() == 'content A' 
    assert file_c.exists() and file_c.read_text() == 'content B' 

def test_checkout_aborts_when_untracked_file_in_the_way_of_rename(temp_repo: Repository) -> None:
    source_file = temp_repo.working_dir / 'old_name.txt'
    source_file.write_text('file data')
    commit_ref1 = temp_repo.commit_working_dir('Author', 'Base commit')

    dest_file = temp_repo.working_dir / 'new_name.txt'
    source_file.rename(dest_file)
    commit_ref2 = temp_repo.commit_working_dir('Author', 'Rename file')

    temp_repo.checkout(commit_ref1)
    assert source_file.exists()
    assert not dest_file.exists()

    untracked_content = 'do not crush me'
    dest_file.write_text(untracked_content)

    with raises(RepositoryError):
        temp_repo.checkout(commit_ref2)

    assert dest_file.read_text() == untracked_content
    assert source_file.exists()
    assert temp_repo.head_commit() == commit_ref1


def test_checkout_deletions_preserve_untracked_files_in_removed_directories(temp_repo: Repository) -> None:
    base_file = temp_repo.working_dir / 'base.txt'
    base_file.write_text('base')
    commit_ref1 = temp_repo.commit_working_dir('Author', 'Base commit')

    config_dir = temp_repo.working_dir / 'config'
    config_dir.mkdir()
    tracked_file = config_dir / 'settings.ini'
    tracked_file.write_text('tracked data')
    temp_repo.commit_working_dir('Author', 'Add config dir')

    untracked_file = config_dir / 'local_secrets.env'
    untracked_content = 'do not delete me'
    untracked_file.write_text(untracked_content)

    temp_repo.checkout(commit_ref1)

    assert not tracked_file.exists()
    assert untracked_file.exists()
    assert config_dir.exists()
    assert untracked_file.read_text() == untracked_content
    assert temp_repo.head_commit() == commit_ref1


def test_checkout_handles_direct_swap_safely(temp_repo: Repository) -> None:
    file_a = temp_repo.working_dir / 'a.txt'
    file_b = temp_repo.working_dir / 'b.txt'
    file_a.write_text('content A')
    file_b.write_text('content B')
    commit_ref1 = temp_repo.commit_working_dir('Author', 'Base commit')

    temp_file = temp_repo.working_dir / 'temp.txt'
    file_a.rename(temp_file)
    file_b.rename(file_a)
    temp_file.rename(file_b)
    commit_ref2 = temp_repo.commit_working_dir('Author', 'Swap A and B')

    temp_repo.checkout(commit_ref1)
    assert file_a.read_text() == 'content A'
    assert file_b.read_text() == 'content B'

    temp_repo.checkout(commit_ref2)

    assert file_a.read_text() == 'content B'
    assert file_b.read_text() == 'content A'


def test_checkout_allows_missing_file_if_target_deletes_it(temp_repo: Repository) -> None:
    target_file = temp_repo.working_dir / 'obsolete.txt'
    target_file.write_text('old data')
    commit_ref1 = temp_repo.commit_working_dir('Author', 'Add file')

    target_file.unlink()
    commit_ref2 = temp_repo.commit_working_dir('Author', 'Remove file')

    temp_repo.checkout(commit_ref1)
    assert target_file.exists()

    target_file.unlink()

    temp_repo.checkout(commit_ref2)

    assert not target_file.exists()
    assert temp_repo.head_commit() == commit_ref2


def test_checkout_aborts_when_untracked_file_blocks_directory(temp_repo: Repository) -> None:
    base_file = temp_repo.working_dir / 'base.txt'
    base_file.write_text('base')
    commit_ref1 = temp_repo.commit_working_dir('Author', 'Base commit')

    nested_dir = temp_repo.working_dir / 'docs'
    nested_dir.mkdir()
    nested_file = nested_dir / 'notes.txt'
    nested_file.write_text('nested data')
    commit_ref2 = temp_repo.commit_working_dir('Author', 'Add nested file')

    temp_repo.checkout(commit_ref1)
    
    blocking_file = temp_repo.working_dir / 'docs'
    blocking_file.write_text('I am a file, not a directory')

    with raises(RepositoryError):
        temp_repo.checkout(commit_ref2)

    assert blocking_file.is_file()
    assert blocking_file.read_text() == 'I am a file, not a directory'
    assert temp_repo.head_commit() == commit_ref1


def test_checkout_handles_file_directory_mutation(temp_repo) -> None:
    data_path = temp_repo.working_dir / 'data'
    data_path.write_text('Just a file')
    file_commit_hash = temp_repo.commit_working_dir('Mor', 'File commit')

    data_path.unlink()  # Delete the file
    data_path.mkdir()   # Create the directory
    (data_path / 'info.txt').write_text('Inside a folder')
    folder_commit_hash = temp_repo.commit_working_dir('Mor', 'Folder commit')

    # Verify we are currently in the folder state
    assert data_path.is_dir()
    assert (data_path / 'info.txt').exists()

    # This should not crash, and should completely obliterate the directory
    temp_repo.checkout(file_commit_hash)

    # 'data' must be a file again, containing the original text
    assert data_path.exists()
    assert data_path.is_file()
    assert data_path.read_text() == 'Just a file'
    
    # And if we go back...
    temp_repo.checkout(folder_commit_hash)
    assert data_path.is_dir()
    assert (data_path / 'info.txt').read_text() == 'Inside a folder'