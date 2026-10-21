"""Journaux techniques hors de l'interface ; les exceptions restent visibles."""
from contextlib import contextmanager, redirect_stdout, redirect_stderr
from datetime import datetime, timezone
from pathlib import Path
import traceback


@contextmanager
def diagnostic_output(workdir, stage):
    folder=Path(workdir)/'diagnostics'
    folder.mkdir(parents=True,exist_ok=True)
    path=folder/(stage+'.log')
    with path.open('w',encoding='utf-8') as stream:
        stream.write(datetime.now(timezone.utc).isoformat()+' '+stage+'\n')
        with redirect_stdout(stream), redirect_stderr(stream):
            try:
                yield path
            except BaseException:
                traceback.print_exc(file=stream)
                raise
            else:
                stream.write('\nTermine sans erreur.\n')
