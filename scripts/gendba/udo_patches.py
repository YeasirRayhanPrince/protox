#!/usr/bin/env python3
"""
udo_patches.py -- runtime fixes for the UDO submodule.

Applied by importing this module and calling apply(). Nothing is edited inside UDO/,
so the submodule checkout stays clean and the fixes travel with our harness — the same
approach we used for index_selection_evaluation's _prepare_query bug.
"""
from __future__ import annotations

import os as _os
# Three roots, overridable so the harness is not welded to one machine layout.
# Defaults match what scripts/cloudlab/provision.sh builds.
#   GENDBA_REPO   the repo (persists: CloudLab project dir)
#   GENDBA_BUILD  postgres build, conda envs, logs   (node-local, rebuilt)
#   GENDBA_DATA   snapshots and generated data        (node-local, rebuilt)
GENDBA_REPO = _os.environ.get("GENDBA_REPO", "/proj/pmoss-PG0/protox")
GENDBA_BUILD = _os.environ.get("GENDBA_BUILD", "/mnt/protox")
GENDBA_DATA = _os.environ.get("GENDBA_DATA", "/data/protox")

import logging
from pathlib import Path

from plumbum import local



def apply():
    _patch_set_system_parameter()


def _patch_set_system_parameter():
    """
    UDO/udo/drivers/postgresdriver.py:304 restarts PostgreSQL through a HARDCODED
    author path:

        local["/mnt/nvme0n1/wz2/noisepage/pg_ctl"]["-D", "/mnt/nvme0n1/wz2/noisepage/pgdata", ...]

    Every other call in that file uses the configured location instead
    (`self.benchmark[3]` = pg_path, `self.benchmark[4]` = pg_data), so this one line is
    simply inconsistent with the rest of the fork. It sits in set_system_parameter,
    i.e. the knob-application path — precisely the "light action" UDO exists to
    explore — so on any machine but the author's, applying a knob would fail to
    restart the right cluster.

    The replacement mirrors the original method exactly, substituting the configured
    paths and preserving the table-level fillfactor branch.
    """
    from udo.drivers.postgresdriver import PostgresDriver

    def set_system_parameter(self, parameter_sql):
        import re
        if parameter_sql.startswith("fillfactor"):
            # table-level knob: ALTER TABLE ... SET (fillfactor = n) then rewrite
            ff = int(parameter_sql.split("=")[1].strip().rstrip(";"))
            for (tbl,) in self.cursor.execute(
                    "SELECT relname FROM pg_class c JOIN pg_namespace n "
                    "ON n.oid=c.relnamespace WHERE n.nspname='public' "
                    "AND c.relkind='r'").fetchall():
                orig_ff = None
                self.cursor.execute(
                    "SELECT reloptions FROM pg_class WHERE relname=%s", (tbl,))
                row = self.cursor.fetchone()
                if row and row[0]:
                    for record in row[0]:
                        for key, value in re.findall(r"(\w+)=(\w*)", record):
                            if key == "fillfactor":
                                orig_ff = int(value)
                if orig_ff is None or ff != orig_ff:
                    self.cursor.execute(f"ALTER TABLE {tbl} SET (fillfactor = {ff})")
                    self.cursor.execute(f"VACUUM FULL {tbl}")
                    self.cursor.execute("CHECKPOINT")
        else:
            self.cursor.execute("ALTER SYSTEM " + parameter_sql)

        self.close()
        pg_path = self.benchmark[3]           # configured, not hardcoded
        pg_data = self.benchmark[4]
        local[f"{pg_path}/pg_ctl"][
            "-D", f"{pg_path}/{pg_data}",
            "--wait", "-t", "180",
            "-l", f"{pg_path}/pg.log.{self.config['port']}",
            "restart"].run(retcode=None)
        self.connect()

    PostgresDriver.set_system_parameter = set_system_parameter
    logging.info("udo_patches: set_system_parameter now uses the configured pg_path")


if __name__ == "__main__":
    import sys
    sys.path.insert(0, GENDBA_REPO + "/UDO")
    apply()
    from udo.drivers.postgresdriver import PostgresDriver
    src = PostgresDriver.set_system_parameter.__doc__ or ""
    print("patched:", "nvme0n1" not in
          __import__("inspect").getsource(PostgresDriver.set_system_parameter))
