from libcaf.ref import SymRef
from libcaf.repository import Repository
from caf import cli_commands

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