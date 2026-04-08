from libcaf.ref import SymRef
from libcaf.repository import Repository
from caf.cli import cli_commands


def test_checkout_short_branch_name_attaches_head(temp_repo: Repository) -> None:
    # 1. Setup base commit on main
    (temp_repo.working_dir / 'file.txt').write_text('base\n')
    temp_repo.commit_working_dir('QA', 'base')
    
    # 2. Create and checkout feature branch
    temp_repo.add_branch('feature')
    temp_repo.checkout('feature')
    
    # FIX 1: Read the absolute path inside the temporary working directory
    head_file = temp_repo.working_dir / temp_repo.repo_dir / 'HEAD'
    head_content = head_file.read_text().strip()
    
    # FIX 2: Match libcaf's specific format
    assert head_content == 'ref: heads/feature'
    
    # 3. Make a commit on feature, then checkout main (short name)
    (temp_repo.working_dir / 'file.txt').write_text('feature\n')
    temp_repo.commit_working_dir('QA', 'feature change')
    
    temp_repo.checkout('main')
    
    # 4. Verify workspace synced and HEAD attached to main
    assert (temp_repo.working_dir / 'file.txt').read_text() == 'base\n'
    head_content = head_file.read_text().strip()
    assert head_content == 'ref: heads/main'


def test_checkout_empty_branch_in_new_repo(temp_repo: Repository) -> None:
    temp_repo.add_branch('empty-feature')
    temp_repo.checkout('empty-feature')
    
    head_file = temp_repo.working_dir / temp_repo.repo_dir / 'HEAD'
    head_content = head_file.read_text().strip()
    assert head_content == 'ref: heads/empty-feature'


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