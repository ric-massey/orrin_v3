"""Resolve and verify research-report links and input hashes; analysis outputs only."""
import ast
import hashlib
import json
import re
from pathlib import Path
from urllib.parse import unquote

OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[1]
sources = {}


def file_record(path):
    if path.is_file() and OUT not in path.parents:
        sources[str(path.relative_to(ROOT))] = hashlib.sha256(path.read_bytes()).hexdigest()


def resolve(match):
    ref = match.group(1)
    if ref == 'ROOT':
        return str(ROOT)
    relative, sep, name = ref.partition('#')
    p = ROOT / relative
    assert p.is_file(), ref
    file_record(p)
    suffix = ''
    label = relative
    if name:
        nodes = [n for n in ast.walk(ast.parse(p.read_text()))
                 if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and n.name == name]
        assert nodes, ref
        line = min(n.lineno for n in nodes)
        suffix = ':' + str(line)
        label += ':' + name
    return f'[{label}](<{p}{suffix}>)'


def local_link(match):
    label, target = match.groups()
    target = target.strip('<>')
    if target.startswith(('https://', 'http://', '#')):
        return match.group(0)
    target = unquote(target)
    bare = re.sub(r':\d+$', '', target)
    path = Path(bare)
    if not path.is_absolute():
        path = (OUT / path).resolve()
        target = str(path) + (target[len(bare):] if target != bare else '')
    # Generated provenance/validation files are created at the end of this script.
    assert path.exists() or path in (OUT/'report_sources.json', OUT/'validation.json'), target
    file_record(path)
    return f'[{label}](<{target}>)'


if __name__ == '__main__':
    for p in OUT.glob('*.md'):
        text = p.read_text().replace('memory/daemon.py', 'memory/memory_daemon.py').replace('goals/daemon.py', 'goals/goals_daemon.py')
        text = re.sub(r'\{\{([^}]+)\}\}', resolve, text)
        text = re.sub(r'\[([^\]\n]+)\]\(([^)\n]+)\)', local_link, text)
        assert '{{' not in text, p
        p.write_text(text)
    verified = 0
    for manifest in ['input_hashes.json', 'probe_input_hashes.json']:
        for relative, expected in json.loads((OUT/manifest).read_text()).items():
            p = ROOT / relative
            assert hashlib.sha256(p.read_bytes()).hexdigest() == expected, f'Input changed: {relative}'
            verified += 1
    (OUT/'report_sources.json').write_text(json.dumps(sources, indent=2, sort_keys=True)+'\n')
    result = {'source_baseline': '1c51dfb', 'input_hash_checks_passed': verified,
              'linked_repository_files': len(sources),
              'markdown_reports': {p.name: {'words':len(p.read_text().split()),'bytes':p.stat().st_size} for p in OUT.glob('*.md')},
              'validation_scope': 'Local links, referenced definitions, input byte preservation; not scientific peer review or runtime testing.'}
    (OUT/'validation.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2))
