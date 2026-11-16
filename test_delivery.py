import io
import tempfile
import unittest
import zipfile
from pathlib import Path
from download_data import extract_workbook


class DownloadTests(unittest.TestCase):
    def archive(self,names):
        source=io.BytesIO()
        with zipfile.ZipFile(source,'w') as archive:
            for name in names:
                archive.writestr(name,b'workbook-fixture')
        source.seek(0)
        return source

    def test_extracts_expected_workbook_without_using_archive_paths(self):
        with tempfile.TemporaryDirectory() as directory:
            target=Path(directory)/'safe.xlsx'
            extract_workbook(self.archive(['../../online_retail_II.xlsx']),target)
            self.assertEqual(target.read_bytes(),b'workbook-fixture')

    def test_rejects_wrong_or_ambiguous_archive(self):
        for names in [['other.xlsx'],['a/online_retail_II.xlsx','b/online_retail_II.xlsx']]:
            with tempfile.TemporaryDirectory() as directory,self.assertRaises(ValueError):
                extract_workbook(self.archive(names),Path(directory)/'safe.xlsx')


if __name__=='__main__':
    unittest.main()
