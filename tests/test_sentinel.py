import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from env_sentinel import compare, inspect, main, parse


class SentinelTests(unittest.TestCase):
    def test_quotes_comments_multiline_and_bom(self):
        doc = parse('\ufeffexport A="hello # world" # comment\nB=hi # comment\nC=hi#literal\nD=\'one\ntwo\'\n')
        self.assertEqual(doc.values, {'A': 'hello # world', 'B': 'hi', 'C': 'hi#literal', 'D': 'one\ntwo'})
        self.assertFalse(doc.issues)

    def test_invalid_lines_do_not_leak_values(self):
        doc = parse('not-an-assignment-secret\nbad-key=secret\nTOKEN="secret" trailing-secret\nTOKEN=x\nBAD="unclosed-secret')
        report = json.dumps(inspect(doc))
        self.assertNotIn('secret', report)
        self.assertIn('duplicate-key', report)
        self.assertIn('unclosed-quote', report)

    def test_diff_never_compares_or_reports_values(self):
        findings = compare(parse('TOKEN=first-secret\nHOST=localhost'), parse('TOKEN=second-secret\nHOST=production'))
        self.assertEqual(findings, [])

    def test_missing_extra_empty_placeholder(self):
        findings = compare(parse('A=\nB=\nC='), parse('A=\nB=changeme\nD=value'))
        self.assertEqual({f['code'] for f in findings}, {'missing-key', 'extra-key', 'empty-value', 'placeholder-value'})

    def test_allow_extra(self):
        self.assertFalse(compare(parse('A=x'), parse('A=y\nB=z'), True))

    def test_references_literals_and_defaults(self):
        doc = parse("A=${MISSING}\nB='${LITERAL}'\nC=${DEFAULT:-okay}\nD=\\${ESCAPED}\nE=${A}\nF=${EMPTY:?required}\nEMPTY=")
        unresolved = [f for f in inspect(doc) if f['code'] == 'unresolved-reference']
        self.assertEqual({f['reference'] for f in unresolved}, {'MISSING', 'EMPTY'})

    def test_cycles_and_long_chains(self):
        self.assertTrue(any(f['code'] == 'cyclic-reference' for f in inspect(parse('A=${B}\nB=${A}'))))
        text = '\n'.join(f'K{i}=${{K{i+1}}}' for i in range(1500)) + '\nK1500=done'
        self.assertFalse(inspect(parse(text)))

    def test_escaped_quotes(self):
        self.assertFalse(parse('A="say \\"hi\\""').issues)
        self.assertEqual(parse('A="ends\\\\"').values['A'], 'ends\\\\')

    def test_cli_json_and_exit_codes(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'input.env'
            path.write_text('TOKEN=private-value\nEMPTY=', encoding='utf-8')
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                code = main(['check', str(path), '--format', 'json'])
            self.assertEqual(code, 1)
            self.assertFalse(json.loads(out.getvalue())['ok'])
            self.assertNotIn('private-value', out.getvalue())
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                self.assertEqual(main(['template', str(path)]), 0)
            self.assertEqual(out.getvalue(), 'EMPTY=\nTOKEN=\n')

    def test_invalid_reference_and_missing_file(self):
        self.assertEqual(compare(parse('broken secret'), parse('A=x'))[0]['source'], 'reference')
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(main(['check', 'nonexistent/secret.env']), 2)


if __name__ == '__main__':
    unittest.main()
