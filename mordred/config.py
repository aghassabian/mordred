#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#
# Copyright (C) 2017 Bitergia
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
#       Alvaro del Castillo <acs@bitergia.com>
#       Luis Cañas-Díaz <lcanas@bitergia.com>

import configparser
import json
import logging

from grimoire_elk.utils import get_connectors

logger = logging.getLogger(__name__)


class Config():
    """ Class aimed to manage mordred configuration """

    def __init__(self, conf_file):
        self.conf_file = conf_file
        self.raw_conf = None
        self.conf = self.__read_conf_files()

    @classmethod
    def backend_section_params(self):
        # Params that must exists in all backends
        params = {
            "enriched_index": {
                "optional": False,
                "default": None,
                "type": str

            },
            "raw_index": {
                "optional": False,
                "default": None,
                "type": str
            },
            "fetch-cache": {
                "optional": True,
                "default": True,
                "type": bool
            }
        }

        return params

    @classmethod
    def general_params(cls):
        """ Define all the possible config params """

        optional_bool_none = {
            "optional": True,
            "default": None,
            "type": bool
        }
        optional_string_none = {
            "optional": True,
            "default": None,
            "type": str
        }
        optional_int_none = {
            "optional": True,
            "default": None,
            "type": int
        }
        optional_empty_list = {
            "optional": True,
            "default": [],
            "type": list
        }
        no_optional_empty_string = {
            "optional": False,
            "default": "",
            "type": str
        }
        no_optional_true = {
            "optional": False,
            "default": True,
            "type": bool
        }
        optional_false = {
            "optional": True,
            "default": False,
            "type": bool
        }

        params = {}

        # GENERAL CONFIG
        params_general = {
            "general": {
                "sleep": optional_int_none,  # we are not using it
                "min_update_delay": {
                    "optional": True,
                    "default": 60,
                    "type": int
                },
                "kibana":  {
                    "optional": True,
                    "default": "5",
                    "type": str
                },
                "update":  {
                    "optional": False,
                    "default": False,
                    "type": bool
                },
                "short_name": {
                    "optional": False,
                    "default": "Short name",
                    "type": str
                },
                "debug": {
                    "optional": False,
                    "default": True,
                    "type": bool
                },
                "from_date": optional_string_none,  # per data source param now
                "logs_dir": {
                    "optional": False,
                    "default": "logs",
                    "type": str
                },
                "skip_initial_load": {
                    "optional": True,
                    "default": False,
                    "type": bool
                }
            }
        }
        # TODO: Move to general config
        params_projects = {
            "projects": {
                "projects_file": {
                    "optional": False,
                    "default": "projects.json",
                    "type": str
                }
            }
        }

        params_phases = {
            "phases": {
                "collection": no_optional_true,
                "enrichment": no_optional_true,
                "identities": no_optional_true,
                "panels": no_optional_true,
                "track_items": optional_false,
                "report": optional_false
            }
        }

        general_config_params = [params_general, params_projects, params_phases]

        for section_params in general_config_params:
            params.update(section_params)

        # Config provided by tasks
        params_collection = {
            "es_collection": {
                "password": optional_string_none,
                "user": optional_string_none,
                "url": {
                    "optional": False,
                    "default": "http://172.17.0.1:9200",
                    "type": str
                }
            }
        }

        params_enrichment = {
            "es_enrichment": {
                "url": {
                    "optional": False,
                    "default": "http://172.17.0.1:9200",
                    "type": str
                },
                "studies": optional_bool_none,
                "autorefresh": optional_bool_none,
                "user": optional_string_none,
                "password": optional_string_none
            }
        }

        params_report = {
            "report": {
                "start_date": {
                    "optional": False,
                    "default": "1970-01-01",
                    "type": str
                },
                "end_date": {
                    "optional": False,
                    "default": "2100-01-01",
                    "type": str
                },
                "interval": {
                    "optional": False,
                    "default": "quarter",
                    "type": str
                },
                "config_file": {
                    "optional": False,
                    "default": "report.cfg",
                    "type": str
                },
                "data_dir": {
                    "optional": False,
                    "default": "report_data",
                    "type": str
                },
                "filters": optional_empty_list,
                "offset": optional_string_none
            }
        }

        params_sortinghat = {
            "sortinghat": {
                "unaffiliated_group": {
                    "optional": False,
                    "default": "Unknown",
                    "type": str
                },
                "unify_method": {  # not used
                    "optional": True,
                    "default": "fast-matching",
                    "type": str
                },
                "matching": {
                    "optional": False,
                    "default": ["email"],
                    "type": list
                },
                "sleep_for": {
                    "optional": False,
                    "default": 3600,
                    "type": int
                },
                "database": {
                    "optional": False,
                    "default": "sortinghat_db",
                    "type": str
                },
                "host": {
                    "optional": False,
                    "default": "mariadb",
                    "type": str
                },
                "user": {
                    "optional": False,
                    "default": "root",
                    "type": str
                },
                "password": no_optional_empty_string,
                "autoprofile": {
                    "optional": False,
                    "default": ["customer", "git", "github"],
                    "type": list
                },
                "load_orgs": {
                    "optional": True,
                    "default": False,
                    "type": bool
                },
                "orgs_file": optional_string_none,
                "identities_file": optional_empty_list,
                "bots_names": optional_empty_list,
                "no_bots_names": optional_empty_list  # to clean bots in SH
            }
        }

        params_track_items = {
            "track_items": {
                "project": {
                    "optional": False,
                    "default": "TrackProject",
                    "type": str
                },
                "upstream_items_url": no_optional_empty_string,
                "upstream_raw_es_url": no_optional_empty_string,
                "raw_index_gerrit": no_optional_empty_string,
                "raw_index_git": no_optional_empty_string
            }
        }

        tasks_config_params = [params_collection, params_enrichment, params_report,
                               params_sortinghat, params_track_items]

        for section_params in tasks_config_params:
            params.update(section_params)


        return params


    @classmethod
    def create_config_file(cls, file_path):
        logger.info("Creating config file in %s", file_path)
        general_sections = cls.general_params()
        backend_sections = cls.get_backend_sections()

        parser = configparser.ConfigParser()

        sections = list(general_sections.keys())
        sections.sort()
        for section_name in sections:
            parser.add_section(section_name)
            section = general_sections[section_name]
            params = list(section.keys())
            params.sort()
            for param in params:
                parser.set(section_name, param, str(section[param]["default"]))

        sections = backend_sections
        sections.sort()
        backend_params = cls.backend_section_params()
        params = list(cls.backend_section_params().keys())
        params.sort()
        for section_name in sections:
            parser.add_section(section_name)
            for param in params:
                if param == "enriched_index":
                    val = section_name
                elif param == "raw_index":
                    val = section_name+"-raw"
                else:
                    val = backend_params[param]['default']
                parser.set(section_name, param, str(val))

        with open(file_path, "w") as f:
            parser.write(f)

    def get_conf(self):
        return self.conf

    @classmethod
    def get_backend_sections(cls):
        # a backend name could include and extra ":<param>"
        # to have several backend entries with different configs
        gelk_backends = list(get_connectors().keys())
        extra_backends = ["google_hits", "remo:activities"]

        return gelk_backends + extra_backends

    @classmethod
    def check_config(cls, config):
        # First let's check all common sections entries
        check_params = cls.general_params()
        backend_sections = cls.get_backend_sections()

        for section in config.keys():
            if section in backend_sections or section[1:] in backend_sections:
                # backend_section or *backend_section, to be checked later
                continue
            if section not in check_params.keys():
                raise RuntimeError("Wrong section:", section)
            # Check the params for the section
            for param in config[section].keys():
                if param not in check_params[section]:
                    raise RuntimeError("Wrong section param:", section, param)
            for param in check_params[section]:
                if param not in config[section].keys():
                    if not check_params[section][param]['optional']:
                        raise RuntimeError("Missing section param:", section, param)
                    else:
                        # Add the default value for this param
                        config[section][param] = check_params[section][param]['default']
                else:
                    ptype = type(config[section][param])
                    ptype_ok = check_params[section][param]["type"]
                    if ptype != ptype_ok:
                        msg = "Wrong type for section param: %s %s %s should be %s" % \
                              (section, param, ptype, ptype_ok)
                        raise RuntimeError(msg)

        # And now the backend_section entries
        # A backend section entry could have specific perceval params which are
        # not checked
        check_params = cls.backend_section_params()
        for section in config.keys():
            # [data_source] or [*data_source]
            if section in backend_sections or section[1:] in backend_sections:
                # backend_section or *backend_section
                for param in check_params:
                    if param not in config[section].keys():
                        if not check_params[param]['optional']:
                            raise RuntimeError("Missing section param:", section, param)
                    else:
                        ptype = type(config[section][param])
                        ptype_ok = check_params[param]["type"]
                        if ptype != ptype_ok:
                            msg = "Wrong type for section param: %s %s %s should be %s" % \
                                  (section, param, ptype, ptype_ok)
                            raise RuntimeError(msg)

    def __add_types(self, raw_conf):
        """ Convert to int, boolean, list, None types config items """

        typed_conf = {}

        for s in raw_conf.keys():
            typed_conf[s] = {}
            for option in raw_conf[s]:
                val = raw_conf[s][option]
                if len(val) > 1  and (val[0] == '"' and val[-1] == '"'):
                    # It is a string
                    typed_conf[s][option] = val[1:-1]
                # Check list
                elif len(val) > 1 and (val[0] == '[' and val[-1] == ']'):
                    # List value
                    typed_conf[s][option] = val[1:-1].replace(' ', '').split(',')
                # Check boolean
                elif val.lower() in ['true', 'false']:
                    typed_conf[s][option] = True if val.lower() == 'true' else False
                # Check None
                elif val.lower() is 'none':
                    typed_conf[s][option] = None
                else:
                    try:
                        # Check int
                        typed_conf[s][option] = int(val)
                    except ValueError:
                        # Is a string
                        typed_conf[s][option] = val
        return typed_conf

    def __read_conf_files(self):
        logger.debug("Reading conf files")
        parser = configparser.ConfigParser()
        parser.read(self.conf_file)
        raw_conf = {s:dict(parser.items(s)) for s in parser.sections()}
        config = self.__add_types(raw_conf)

        self.check_config(config)

        projects_file = config['projects']['projects_file']
        with open(projects_file, 'r') as fd:
            projects = json.load(fd)
        config['projects_data'] = projects

        return config
