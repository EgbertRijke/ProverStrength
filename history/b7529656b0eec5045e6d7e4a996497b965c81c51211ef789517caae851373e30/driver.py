"""First fixed, local smoke observation; retained with its generated evidence."""

import hashlib
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
from datetime import datetime, timezone

ROOT = Path('/Users/egbertrijke/Repositories/ProverStrength')
PRODUCT = Path('/Users/egbertrijke/Repositories/agda-prover-dev/agda-prover')
REVISION = 'd2b0d7c488b5a478fb5cc464509345b6c74c9b01'
EVALUATOR = '25024ccf30f77fd661e78abe1689564b937bd9f2'
AGDA = '/Users/egbertrijke/.cabal/store/ghc-9.6.7/Agd-2.8.0-08e6f886/bin/agda'
OUT = ROOT / 'runs/smoke-v2-d2b0d7c-20260910'
OUT.mkdir(exist_ok=False)


def git(repo, *args):
    return subprocess.check_output(['git', '-C', str(repo), *args]).decode().strip()


def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def save(name, value):
    with (OUT / name).open('x', encoding='utf-8') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write('\n')


def snapshot(repo, revision, name):
    archive = OUT / (name + '.tar')
    with archive.open('xb') as stream:
        subprocess.run(['git', '-C', str(repo), 'archive', '--format=tar', revision],
                       stdout=stream, check=True)
    destination = OUT / name
    destination.mkdir()
    subprocess.run(['tar', '-xf', str(archive), '-C', str(destination)], check=True)
    return destination


def source_hashes(root):
    return {str(p.relative_to(root)): sha(p) for p in sorted(root.rglob('*')) if p.is_file()}


assert git(PRODUCT, 'rev-parse', 'HEAD') == REVISION
assert not git(PRODUCT, 'status', '--porcelain', '--untracked-files=all')
product = snapshot(PRODUCT, REVISION, 'product')
evaluator = snapshot(ROOT, EVALUATOR, 'evaluator')
hashes = {'product': source_hashes(product), 'evaluator': source_hashes(evaluator)}
for name in tuple(os.environ):
    if name.startswith('AGDAPROVER_') or name in ('PYTHONPATH', 'PYTHONHOME', 'AGDA_DIR', 'AGDA_DATA_DIR'):
        os.environ.pop(name)
os.environ.update(PYTHONDONTWRITEBYTECODE='1', PYTHONHASHSEED='0', LC_ALL='en_US.UTF-8')
sys.path.insert(0, str(evaluator / 'src'))
from prover_strength.cli import markdown
from prover_strength.data import digest
from prover_strength.model import rate
from prover_strength.runner import run


def command(snapshot, module):
    return [sys.executable, '-B', '-S', '-c',
            f'import sys; sys.path.insert(0, {str(snapshot / "src")!r}); from {module} import main; raise SystemExit(main())']


provers = [
    {'id': 'lambda-baseline-v1', 'revision': EVALUATOR, 'adapter': 'candidate-json',
     'argv': command(evaluator, 'prover_strength.cli') +
             ['baseline', '{source}', '--agda', '{agda}', '--budget', '{budget}']},
    {'id': 'AgdaProver-d2b0d7c-symbolic-deep', 'revision': REVISION, 'adapter': 'agdaprover',
     'argv': command(product, 'agdaprover.cli') +
             ['prove-prefix', '{source}', '--agda', '{agda}', '--deep', '--ranker', 'symbolic', '--timeout', '{budget}']},
]
suite = json.loads((evaluator / 'examples/smoke-suite.json').read_text())
assert len(suite['tasks']) == 16
save('provers.json', provers)
manifest = {
    'schema_version': 'prover-strength.commit-observation.v1',
    'started_at': datetime.now(timezone.utc).isoformat(),
    'product_commit': REVISION, 'product_tree': git(PRODUCT, 'rev-parse', REVISION + '^{tree}'),
    'evaluator_commit': EVALUATOR, 'evaluator_tree': git(ROOT, 'rev-parse', EVALUATOR + '^{tree}'),
    'driver_sha256': sha(Path(__file__)), 'source_hashes': hashes,
    'archive_sha256': {n: sha(OUT / (n + '.tar')) for n in hashes},
    'suite_id': digest(suite), 'suite_file_sha256': sha(evaluator / 'examples/smoke-suite.json'),
    'profile': {'ranker': 'symbolic', 'search': 'deep', 'model': None, 'action_model': None,
                'budget_seconds': 10, 'max_candidates': 8000, 'seeds': [0], 'order_seed': 0,
                'max_output_bytes': 16777216, 'reference_check_budget_seconds': 60},
    'environment': {'id': 'm3-max-36gb-macos26.6.2-agda2.8-stock-offline-v1',
                    'platform': platform.platform(), 'python': sys.version,
                    'python_sha256': sha(Path(sys.executable).resolve()),
                    'cpu': subprocess.check_output(['sysctl', '-n', 'machdep.cpu.brand_string']).decode().strip(),
                    'memory_bytes': int(subprocess.check_output(['sysctl', '-n', 'hw.memsize'])),
                    'network': 'inherited macOS sandbox-exec deny network*',
                    'workers': 1, 'python_hash_seed': 0, 'product_environment_overrides': {},
                    'model_override': None, 'site_packages': 'disabled in workers',
                    'cache_policy': 'new task and independent-check directories; immutable sources; warm Agda builtin installation'},
}
save('observation.json', manifest)
print('START', REVISION, '16 tasks x 2 provers; 10 s/trial', flush=True)
result = run(suite, provers, agda=AGDA, budget=10,
             environment_id=manifest['environment']['id'], seeds=[0], artifacts=OUT / 'artifacts')
after = {'product': source_hashes(product), 'evaluator': source_hashes(evaluator)}
if hashes != after:
    save('source-mutation.json', {'status': 'invalid-measurement', 'after': after})
    raise RuntimeError('frozen evaluated sources changed during measurement')
save('results.json', result)
report = rate(result, 'lambda-baseline-v1', bootstrap=200, seed=0)
save('ratings.json', report)
with (OUT / 'report.md').open('x', encoding='utf-8') as stream:
    stream.write(markdown(report))
save('completed.json', {'finished_at': datetime.now(timezone.utc).isoformat(),
                        'source_integrity': 'unchanged', 'results_sha256': sha(OUT / 'results.json'),
                        'ratings_sha256': sha(OUT / 'ratings.json')})
print(markdown(report), flush=True)
