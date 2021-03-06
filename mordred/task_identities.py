#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#
# Copyright (C) 2016 Bitergia
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 59 Temple Place - Suite 330, Boston, MA 02111-1307, USA.
#
# Authors:
#     Luis Cañas-Díaz <lcanas@bitergia.com>
#     Alvaro del Castillo <acs@bitergia.com>
#

import base64
import gzip
import json
import logging
import shutil
import subprocess
import tempfile

import requests

from queue import Empty

from mordred.task import Task
from mordred.task_manager import TasksManager
from sortinghat import api
from sortinghat.cmd.init import Init
from sortinghat.cmd.load import Load
from sortinghat.cmd.export import Export
from sortinghat.command import CMD_SUCCESS
from sortinghat.db.database import Database
from sortinghat.db.model import Profile

from grimoire_elk.arthur import load_identities

logger = logging.getLogger(__name__)


class TaskInitSortingHat(Task):
    """ Class aimed to create the SH database """

    def __init__(self, config):
        super().__init__(config)

        self.sh_kwargs = {'user': self.db_user, 'password': self.db_password,
                          'database': self.db_sh, 'host': self.db_host,
                          'port': None}

    def execute(self):
        code = Init(**self.sh_kwargs).run(self.db_sh)

        if code != 0:
            logger.warning("Can not create the SortingHat database")

        logger.debug("Sortinghat initialized")


class TaskIdentitiesCollection(Task):
    """ Class aimed to get identites from raw data """

    def __init__(self, config, load_ids=True):
        super().__init__(config)

        self.load_ids = load_ids  # Load identities from raw index
        self.sh_kwargs = {'user': self.db_user, 'password': self.db_password,
                          'database': self.db_sh, 'host': self.db_host,
                          'port': None}

    def execute(self):

        #FIXME this should be called just once
        # code = 0 when command success
        code = Init(**self.sh_kwargs).run(self.db_sh)

        if not self.backend_section:
            logger.error("Backend not configured in TaskIdentitiesCollection %s", self.backend_section)
            return

        backend_conf = self.config.get_conf()[self.backend_section]

        if 'collect' in backend_conf and not backend_conf['collect']:
            logger.info("Don't load ids from a backend without collection %s", self.backend_section)
            return

        if self.load_ids:
            logger.info("[%s] Gathering identities from raw data", self.backend_section)
            enrich_backend = self._get_enrich_backend()
            ocean_backend = self._get_ocean_backend(enrich_backend)
            load_identities(ocean_backend, enrich_backend)
            #FIXME get the number of ids gathered


class TaskIdentitiesLoad(Task):
    def __init__(self, config):
        super().__init__(config)

        self.sh_kwargs = {'user': self.db_user, 'password': self.db_password,
                          'database': self.db_sh, 'host': self.db_host,
                          'port': None}

    def is_backend_task(self):
        return False

    def execute(self):

        def is_remote(filename):
            """ Naive implementation. To be evolved """
            remote = False
            if 'http' in filename:
                return True
            return remote

        def load_identities_file(filename):
            """ Load an identities file in Sortinghat """
            logger.info("[sortinghat] Loading identities from file %s", filename)
            code = Load(**self.sh_kwargs).run("--identities", filename)
            if code != CMD_SUCCESS:
                logger.error("[sortinghat] Error loading %s", filename)


        cfg = self.config.get_conf()

        # code = 0 when command success
        code = Init(**self.sh_kwargs).run(self.db_sh)

        if 'load_orgs' in cfg['sortinghat'] and cfg['sortinghat']['load_orgs']:
            if 'orgs_file' not in cfg['sortinghat'] or not cfg['sortinghat']['orgs_file']:
                raise RuntimeError("Load orgs active but no orgs_file configured")
            logger.info("[sortinghat] Loading orgs from file %s", cfg['sortinghat']['orgs_file'])
            code = Load(**self.sh_kwargs).run("--orgs", cfg['sortinghat']['orgs_file'])
            if code != CMD_SUCCESS:
                logger.error("[sortinghat] Error loading %s", cfg['sortinghat']['orgs_file'])
            #FIXME get the number of loaded orgs

        if 'identities_file' in cfg['sortinghat']:
            filenames = cfg['sortinghat']['identities_file']
            for filename in filenames:
                filename = filename.replace(' ', '')  # spaces used in config file list
                if filename == '':
                    continue
                if is_remote(filename):
                    res_get = requests.get(filename)
                    res_get.raise_for_status()
                    with tempfile.NamedTemporaryFile() as temp:
                        temp.write(res_get.content)
                        temp.flush()
                        load_identities_file(temp.name)
                else:
                    load_identities_file(filename)


class TaskIdentitiesExport(Task):
    def __init__(self, config):
        super().__init__(config)

        self.sh_kwargs = {'user': self.db_user, 'password': self.db_password,
                          'database': self.db_sh, 'host': self.db_host,
                          'port': None}

    def is_backend_task(self):
        return False

    def execute(self):

        def export_identities(filename):
            """ Export Sortinghat identities to a file """
            logger.info("[sortinghat] Exporting identities to %s", filename)
            code = Export(**self.sh_kwargs).run("--identities", filename)
            if code != CMD_SUCCESS:
                logger.error("[sortinghat] Error exporting %s", filename)

        cfg = self.config.get_conf()

        if cfg['sortinghat']['identities_export_url'] is None:
            return

        if cfg['sortinghat']['github_api_token'] is None:
            logger.error("github_api_token for uploading data to GitHub not found in sortinghat section")
            return

        repo_file_sha = None
        gzipped_identities_file = None
        github_token = cfg['sortinghat']['github_api_token']
        headers = {"Authorization": "token " + github_token}

        repository_url = cfg['sortinghat']['identities_export_url']
        try:
            # https://github.com/<owner>/<repo>/blob/<branch>/<sh_identities>.gz
            repo_file = repository_url.rsplit("/", 1)[1]
            repository_raw = repository_url.rsplit("/", 1)[0]
            repository = repository_raw.rsplit("/", 2)[0]
            repository_api = repository.replace('github.com', 'api.github.com/repos')
            # repository_type = repository_raw.rsplit("/", 2)[1]
            repository_branch = repository_raw.rsplit("/", 2)[2]
        except IndexError as ex:
            logger.error("Can not export identities to: %s", repository_url)
            logger.debug("Expected format: https://github.com/owner/repo/blob/master/file")
            logger.debug(ex)
            return

        with tempfile.NamedTemporaryFile() as temp:
            export_identities(temp.name)
            logger.debug("SH identities exported to tmp file: %s", temp.name)
            # Compress the file with gzip
            with open(temp.name, 'rb') as f_in:
                gzipped_identities_file = temp.name + '.gz'
                with gzip.open(gzipped_identities_file, 'wb') as f_out:
                    shutil.copyfileobj(f_in, f_out)
            # Get sha for the repository_file
            url_dir = repository_api + "/git/trees/"+ repository_branch
            logger.debug("Gettting sha data from tree: %s", url_dir)
            raw_repo_file_info = requests.get(url_dir, headers=headers)
            raw_repo_file_info.raise_for_status()
            for rfile in raw_repo_file_info.json()['tree']:
                if rfile['path'] == repo_file:
                    logger.debug("SHA found: %s, ", rfile["sha"])
                    repo_file_sha = rfile["sha"]

            if repo_file_sha is None:
                logger.debug("Can not find sha for %s. It will be created.", repository_url)

            # Upload gzipped file to repository_file
            logger.debug("Encoding to base64 identities file")
            with open(gzipped_identities_file, "rb") as raw_file:
                base64_raw = base64.b64encode(raw_file.read())
                # base64 is ascii encoded data
                gzipped_base64_identities = base64_raw.decode('ascii')
                upload_json = {
                    "content": gzipped_base64_identities,
                    "message": "mordred automatic update"
                }
                if repo_file_sha:
                    upload_json["sha"] = repo_file_sha

                data = json.dumps(upload_json)
                url_put = repository_api + "/contents/"+ repo_file
                logger.debug("Uploading to GitHub %s", url_put)
                upload_res = requests.put(url_put, headers=headers, data=data)
                upload_res.raise_for_status()


class TaskIdentitiesMerge(Task):
    """ Basic class shared by all Sorting Hat tasks """

    def __init__(self, conf, load_orgs=True, load_ids=True, unify=True,
                 autoprofile=True, affiliate=True, bots=True):
        super().__init__(conf)

        self.load_ids = load_ids  # Load identities from raw index
        self.unify = unify  # Unify identities
        self.autoprofile = autoprofile  # Execute autoprofile
        self.affiliate = affiliate # Affiliate identities
        self.bots = bots # Mark bots in SH
        self.sh_kwargs={'user': self.db_user, 'password': self.db_password,
                        'database': self.db_sh, 'host': self.db_host,
                        'port': None}
        self.db = Database(**self.sh_kwargs)

    def is_backend_task(self):
        return False

    def __get_uuids_from_profile_name(self, profile_name):
        """ Get the uuid for a profile name """
        uuids = []

        with self.db.connect() as session:
            query = session.query(Profile).\
            filter(Profile.name == profile_name)
            profiles = query.all()
            if profiles:
                for p in profiles:
                    uuids.append(p.uuid)
        return uuids

    def __build_sh_command(self):
        cfg = self.config.get_conf()

        db_user = cfg['sortinghat']['user']
        db_password = cfg['sortinghat']['password']
        db_host = cfg['sortinghat']['host']
        db_name = cfg['sortinghat']['database']
        cmd = ['sortinghat', '-u', db_user, '-p', db_password, '--host', db_host,
               '-d', db_name]

        return cmd

    def __execute_sh_command(self, cmd):
        logger.debug("Executing %s", cmd)
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE)
        outs, errs = proc.communicate()
        uuids = self.__get_uuids_to_refresh(outs.decode("utf8"))
        return_code = proc.returncode
        if return_code != 0:
            logger.error("[sortinghat] Error in command %s", cmd)
            uuids = []
        return uuids

    def __get_uuids_to_refresh(self, data):
        """
        Return the Sortinggat unique identifiers that must be refreshed
        after a unify and affiliate command

        Formats:
        Unique identity ab882b9c6f29837b263448aeb6eab1ec373d7688 merged on 75fc28ef4643de5323e89fb26e4e67c97b24f507
        Unique identity 12deb94aa946193e28c2a933cbee4b338a928042 (acs_at_bitergia.com) affiliated to Bitergia
        """

        if data is None:
            return None

        lines = data.split("\n")
        uuids = []
        for line in lines:
            fields = line.split()
            if 'merged' in line:
                uuids.append(fields[2])
            elif 'affiliated' in line:
                uuids.append(fields[2])
        return uuids

    def do_affiliate(self):
        cmd = self.__build_sh_command()
        cmd += ['affiliate']
        uuids = self.__execute_sh_command(cmd)
        return uuids

    def do_autoprofile(self, sources):
        cmd = self.__build_sh_command()
        cmd += ['autoprofile'] + sources
        self.__execute_sh_command(cmd)
        return None

    def do_unify(self, kwargs):
        cmd = self.__build_sh_command()
        cmd += ['unify', '--fast-matching', '-m', kwargs['matching']]
        uuids = self.__execute_sh_command(cmd)
        return uuids

    def execute(self):
        cfg = self.config.get_conf()

        uuids_refresh = []

        if self.unify:
            for algo in cfg['sortinghat']['matching']:
                kwargs = {'matching':algo, 'fast_matching':True}
                logger.info("[sortinghat] Unifying identities using algorithm %s",
                            kwargs['matching'])
                uuids = self.do_unify(kwargs)
                uuids_refresh += uuids
                logger.debug("uuids to refresh from unify: %s", uuids)

        if self.affiliate:
            # Global enrollments using domains
            logger.info("[sortinghat] Executing affiliate")
            uuids = self.do_affiliate()
            uuids_refresh += uuids
            logger.debug("uuids to refresh from affiliate: %s", uuids)

        if self.autoprofile:
            if not 'autoprofile' in cfg['sortinghat']:
                logger.info("[sortinghat] Autoprofile not configured. Skipping.")
            else:
                logger.info("[sortinghat] Executing autoprofile for sources: %s",
                            cfg['sortinghat']['autoprofile'])
                sources = cfg['sortinghat']['autoprofile']
                self.do_autoprofile(sources)

        # The uuids must be refreshed in all backends (data sources)
        # Give 5s so the queue is filled and if not, continue without it
        try:
            autorefresh_backends_uuids = TasksManager.UPDATED_UUIDS_QUEUE.get(timeout=5)
            for backend_section in autorefresh_backends_uuids:
                autorefresh_backends_uuids[backend_section] += uuids_refresh
            TasksManager.UPDATED_UUIDS_QUEUE.put(autorefresh_backends_uuids)
            logger.debug("Autorefresh uuids queue after processing identities: %s", autorefresh_backends_uuids)
        except Empty:
            logger.warning("Autorefresh uuids not active because the queue for it is empty.")

        if self.bots:
            if not 'bots_names' in cfg['sortinghat']:
                logger.info("[sortinghat] Bots name list not configured. Skipping.")
            else:
                logger.info("[sortinghat] Marking bots: %s",
                            cfg['sortinghat']['bots_names'])
                for name in cfg['sortinghat']['bots_names']:
                    # First we need the uuids for the profile name
                    uuids = self.__get_uuids_from_profile_name(name)
                    # Then we can modify the profile setting bot flag
                    profile = {"is_bot": True}
                    for uuid in uuids:
                        api.edit_profile(self.db, uuid, **profile)
                # For quitting the bot flag - debug feature
                if 'no_bots_names' in cfg['sortinghat']:
                    logger.info("[sortinghat] Removing Marking bots: %s",
                                cfg['sortinghat']['no_bots_names'])
                    for name in cfg['sortinghat']['no_bots_names']:
                        uuids = self.__get_uuids_from_profile_name(name)
                        profile = {"is_bot": False}
                        for uuid in uuids:
                            api.edit_profile(self.db, uuid, **profile)

        # Autorefresh must be done once identities processing has finished
        # Give 5s so the queue is filled and if not, continue without it
        try:
            autorefresh_backends = TasksManager.AUTOREFRESH_QUEUE.get(timeout=5)
            for backend_section in autorefresh_backends:
                autorefresh_backends[backend_section] = True
            TasksManager.AUTOREFRESH_QUEUE.put(autorefresh_backends)
            logger.debug("Autorefresh queue after processing identities: %s", autorefresh_backends)
        except Empty:
            logger.warning("Autorefresh not active because the queue for it is empty.")
