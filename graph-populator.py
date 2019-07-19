#!/usr/bin/python
###############################################################################
# Copyright 2019 Lukas Genssler (lukas.genssler@icloud.com)                   #                             
#                Chair of Mobile Systems, University of Bamberg               #                            
#                                                                             #
#    Licensed under the Apache License, Version 2.0 (the "License");          #                     
#    you may not use this file except in compliance with the License.         #                     
#    You may obtain a copy of the License at                                  #
#                                                                             #         
#      http://www.apache.org/licenses/LICENSE-2.0                             # 
#                                                                             #
#    Unless required by applicable law or agreed to in writing, software      #
#    distributed under the License is distributed on an "AS IS" BASIS,        #                     
#    WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. #                             
#    See the License for the specific language governing permissions and      #
#    limitations under the License.                                           #
###############################################################################



import getopt
import importlib
import logging
import pprint
import sys
import py2neo
import neo4j

#########################
# Class Handling Import #
#########################

class DomainModelCreator:

    #
    # Establish db-connection
    #
    def setup_db_connection(self):
        
        self.neo4j_connection = py2neo.Graph(self.db_url, auth=(self.db_user, self.db_pwd))
        print_info("Establishing database connection with " + self.db_url + " ... ")
        self.neo4j_connection.run("MATCH (n) DETACH DELETE n")
        self.neo4j_connection.run("CREATE CONSTRAINT ON (n:TBox) ASSERT n.identifier IS UNIQUE")
        print_info("Database cleard")

        if self.opt_verbose or self.opt_v_verbose:
            print_info("Connection established ...")

        if self.neo4j_connection is None:
            print_warning("Not connected to any database! Printing queries to std-out!")


    #
    # Helper function deciding what to do with query.
    # If no db-connection is established, print it to std_out.
    # If db-connection is established, execute query.
    # Iheck if any verbose mode is active and print accoriding mesages to std_out.
    #
    def execute_query(self, query, verbose_msg):
        if self.neo4j_connection is None:
            print(query)
        else:
            if self.opt_verbose:
                print("// " + verbose_msg)
                # Question: Should the verbose_msg also be cypher compatible or do I use
                # this only if I want to see whats happening? 
            if self.opt_v_verbose:
                print(query)
            try: 
                self.neo4j_connection.run(query)
            except Exception as e: 
                print_warning(e)


    #
    # Import all all python dict files stated as arguments as modules dynamically
    # Basic validity checks. Exits early and loudly if the imported dicts are faulty!
    # Returns list of imported modules.
    #
    def import_data_files(self):

        domain_models = []

        for dict_file in self.arguments:
            try:
                domain_models.append(importlib.import_module(dict_file[0:-3]))
            except Exception as exception:
                print(  "#### ERROR ####: \n" +
                        "A python dict file can not be imported correctly \n" +
                        "Exception Message:\n" + str(exception)
                )
                sys.exit()

        # Checks if imported files contain at least a dict called "classes"
        # Checks if other attributs called "relations" or "namespaces" are availabed and if so dicts 
        # Expected import order is rootclass dict first
        for i, domain_model in enumerate(domain_models):
            if hasattr(domain_model, "classes"):
                if not type(domain_model.classes) is list:
                    raise NoListError(domain_model.__name__, "classes")
            else:
                raise NoClassesListError(domain_model.__name__)

            if hasattr(domain_model, "relations"):
                if not type(domain_model.relations) is list:
                    raise NoListError(domain_model.__name__, "relations")

            if hasattr(domain_model, "namespaces"):
                if not type(domain_model.namespaces) is list:
                    raise NoListError(
                        domain_model.__name__, "namespaces")
            # Rootclass needs namespaces dictornary
            elif not hasattr(domain_model, "namespaces") and i == 0:
                raise UpperMostLevelError(domain_model.__name__, "namespaces")

        return domain_models

    #
    # Creats node creation queries.
    # Dynamically take all properties stated for each node in the dicts.
    # Required properties: "label", "title".
    #
    def create_nodes(self, domain_models):
        # Iterate over all keys ("title" of the nodes) in all "classes"-dicts stored in the imported dicts
        for domain_model in domain_models:
            temp_classes_dict={}
            # for node in domain_model.classes:
            for item in domain_model.classes:
                node = item.keys()[0]
                temp_classes_dict.update(item)

                # KeyError is raised when a requested key (property) is missing.
                # This is the case if there is no "label"-property
                try:
                    query_data= {
                        "label": temp_classes_dict[node]["label"],
                        "identifier": temp_classes_dict[node]["identifier"],
                        "title": node
                    }
                    query = "CREATE(:{label} {{ title: '{title}', identifier: '{identifier}'".format(**query_data)                    

                    for prop in temp_classes_dict[node]:
                        # Omitting "label" property as it is required and handeled always outside of this for loop
                        if prop not in ["label", "identifier", "subclass_of", "required_property", "optional_property"]: # the required properties are omitted, also the ones that will be relations
                            property_data = {
                                    "property_name": str(prop),
                                    "property_value": str(temp_classes_dict[node][prop])
                            }
                            # Properties that are not lists are interpreted as stirngs 
                            if type(temp_classes_dict[node][prop]) is list:
                                query = query + ", {property_name}:{property_value}".format(**property_data)
                            else:
                                query = query + ", {property_name}:'{property_value}'".format(**property_data)

                    query = query + "})"
                    node= self.execute_query(query, "Creating node: " + node)

                except KeyError as missing_key:
                    warning_data = {
                        "domain_model": domain_model.__name__, 
                        "missing_key": str(missing_key), 
                        "node": str(node), 
                        "dict_entry": str(temp_classes_dict[node])
                    }
                    warning_msg = ("A entry in the classes dict in the module '{domain_model}' does not contain a required key." + 
                                    "The missing key is {missing_key} in '{node}': '{dict_entry}'" +
                                    "No node '{node}' can be created! \n").format(**warning_data)
                    print_warning(warning_msg)


        if self.opt_verbose or self.opt_v_verbose:
            print_info("Node creation finished!")

    #
    # Creates relation creation queries for subclass relations.
    # Nodes need to have a "subclass_of" property in order to be considered.
    #
    def create_relations_subclass(self, domain_models):
        for domain_model in domain_models:
            temp_classes_dict={}
            # for node in domain_model.classes:
            for item in domain_model.classes:
                node = item.keys()[0]
                temp_classes_dict.update(item)

                error_data = {
                            "node" : node,
                            "domain_model": domain_model.__name__
                }
                # checking for "subclass_of"-property, if not found display warning
                try:
                    if not(temp_classes_dict[node]["subclass_of"]): raise KeyError('subclass_of')

                    data_type = type(temp_classes_dict[node]["subclass_of"])
                    # only lists (or strings) are allowed as datatypes of the 'subclass_of' property 

                    if data_type is list:
                        #iterate over all "parents" of this node in the list
                        for parent in temp_classes_dict[node]["subclass_of"]:
                            query_data = {
                                "node_lower": node.lower(),
                                "node": node,
                                "parent_lower": parent.lower(),
                                "parent": parent
                            }

                            # Create "MATCH" statement
                            query_match = (
                                "MATCH ({node_lower}:TBox  {{ title: '{node}' }}), ({parent_lower}:TBox {{ title: '{parent}' }})"
                            ).format(**query_data)

                            # Create "CREATE" statement
                            query_create = (
                                "CREATE ({node_lower})-[:subclass_of]->({parent_lower})"
                            ).format(**query_data)

                            # Connect "MACTH" and "CREATE" statements
                            query = query_match + " \n " + query_create + "\n"
                            self.execute_query(query, "Creating subclass relation from {node} to {parent}".format(node = node, parent = parent))

                    elif data_type is str:
                        parent = temp_classes_dict[node]["subclass_of"]
                        query_data = {
                                "node_lower": node.lower(),
                                "node": node,
                                "parent_lower": parent.lower(),
                                "parent": parent
                        }

                        # Create "MATCH" statement
                        query_match = ( 
                                "MATCH ({node_lower}:TBox  {{ title: '{node}' }}), ({parent_lower}:TBox {{ title: '{parent}' }})"
                        ).format(**query_data)

                        # Create "CREATE" statement
                        query_create = (
                                "CREATE ({node_lower})-[:subclass_of]->({parent_lower})"
                        ).format(**query_data)

                        # Connect "MACTH" and "CREATE" statements
                        query = query_match + " \n " + query_create + "\n"
                        self.execute_query(query, "Creating subclass relation from {node} to {parent}".format(**query_data))

                    else:
                        warning_msg = ("The 'subclass_of' property of '{node}' in the module '{domain_model}' is neither a list nor a string." +
                                        "Cannot handle other datatypes. No subclass relation for node '{node}' is created!").format(**error_data)
                        print_warning(warning_msg)
                    

                except KeyError as missing_key:
                    info_msg = ("A entry in the classes dict in the module '{domain_model}' does not have a " + str(missing_key) + " property. " + 
                                "No subclass relation for node '{node}' is created! You can savely ignore this if the node '{node}' " +
                                "is part of the rootclass.").format(**error_data)
                    print_info(info_msg)

            
              

        if self.opt_verbose or self.opt_v_verbose:
            print_info("Subclass relation creation finished!")

    #
    # Creats relation creation queries for object_property relations.
    # Relations need to have a label", "from_entity", "to_entity" and "namespace" property
    #
    def create_relations_objectproperty(self, domain_models):

        for domain_model in domain_models:
            # Check if currently handeled module has a dict called "relations"
            # if not skip this module and display warning
            if hasattr(domain_model, "relations"):
                temp_relations_dict={}
                # Iterate each relation in relations dict to dynamically create all relation querries with its properties
                # KeyError is raised when a requested (required) key is missing.
                # for relation in domain_model.relations:
                for item in domain_model.relations:
                    relation = item.keys()[0]
                    temp_relations_dict.update(item)

                    try:
                        # Create "MATCH" statement, needed to identify the starting and ending nodes
                        query_data = {
                            "from_lower": temp_relations_dict[relation]["from_entity"].lower(),
                            "from": temp_relations_dict[relation]["from_entity"],
                            "to_lower": temp_relations_dict[relation]["to_entity"].lower(),
                            "to": temp_relations_dict[relation]["to_entity"],
                            # "title": temp_relations_dict[relation]["namespace"] + ":" + relation,
                            "title": relation,
                            "namespace": temp_relations_dict[relation]["namespace"],
                            "label": temp_relations_dict[relation]["label"],
                            "identifier": temp_relations_dict[relation]["identifier"]
                        }
                        query_match = ("MATCH ({from_lower}:TBox  {{ title: '{from}' }}), ({to_lower}:TBox {{ title: '{to}' }})").format(**query_data)

                        # Create "CREATE" statement for relation
                        query_create = ("CREATE ({from_lower})-[:{label} {{ title: '{title}', namespace: '{namespace}', identifier: '{identifier}'").format(**query_data)
                        # Iterating over all properties of this relation to add them dynamically
                        for prop in temp_relations_dict[relation]:
                            if prop not in ["label", "from_entity", "namespace", "to_entity", "identifier"]: #the required properties are ommited
                                property_data = {
                                    "property_name": str(prop),
                                    "property_value": str(temp_relations_dict[relation][prop])
                                }
                                # Properties that are not lists are interpreted as stirngs 
                                if type(temp_relations_dict[relation][prop]) is list:
                                    query_create = query_create + ", {property_name}:{property_value}".format(**property_data)
                                else:
                                    query_create = query_create + ", {property_name}:'{property_value}'".format(**property_data)
                            else:
                                pass
                        query_create = query_create + "}}]->({to_lower})".format(**query_data)

                        # connect "MATCH" and "CREATE" statements
                        query = query_match + "\n " + query_create + "\n"
                        self.execute_query(query, "Creating object-property-relation '{title}' from {from} to {to}".format(**query_data))

                    except KeyError as missing_key:
                        error_data = {
                            "domain_model": domain_model.__name__, 
                            "missing_key": str(missing_key), 
                            "relation": str(relation), 
                            "dict_entry": str(temp_relations_dict[relation])
                        }
                        warning_msg = ("A entry in the relations dict does not contain a required key. " + 
                                        "The missing key is {missing_key} in '{relation}: {dict_entry}'. "+ 
                                        "No relation '{relation}' cann be created!").format(**error_data)
                        print_warning(warning_msg)

            else:
                info_msg = ("No dict called 'relations' available in module {} No relations created from this domain-model."+
                            "You can safely ignore this, if this is intended.").format(domain_model.__name__)
                print_info(info_msg)
               

        if self.opt_verbose or self.opt_v_verbose:
            print_info("Object_property relations created!")


    # Create optional and reuired properties (if they dont exist)
    # And create relations between the provided node and the property nodes (the relation will have :TBox l)
    # props is a dict with two keys ("required_properties" & "optional_properties")
    # The values in props is are lists of qualified names
    #
    def create_property_nodes(self, domain_models):
        # Iterate over all keys ("title" of the nodes) in all "properties"-dicts stored in the imported dicts
        for domain_model in domain_models:
            if hasattr(domain_model, "properties"):
                temp_properties_dict={}
                # for node in domain_model.properties:
                for item in domain_model.properties:
                    node = item.keys()[0]
                    temp_properties_dict.update(item)
                    # KeyError is raised when a requested key (property) is missing.
                    # This is the case if there is no "label"-property
                    try:
                        query_data= {
                            "label": temp_properties_dict[node]["label"],
                            "label_2": temp_properties_dict[node]["label2"],
                            #"identifier": temp_properties_dict[node]["identifier"],
                            "title": node
                        }
                        query = "CREATE(:{label}:{label_2} {{ title: '{title}'".format(**query_data)                    

                        for prop in temp_properties_dict[node]:
                            # Omitting "label" property as it is required and handeled always outside of this for loop
                            if prop not in ["label", "label2"]: # the required properties are omitted
                                property_data = {
                                        "property_name": str(prop),
                                        "property_value": str(temp_properties_dict[node][prop])
                                }
                                # Properties that are not lists are interpreted as stirngs 
                                if type(temp_properties_dict[node][prop]) is list:
                                    query = query + ", {property_name}:{property_value}".format(**property_data)
                                else:
                                    query = query + ", {property_name}:'{property_value}'".format(**property_data)
                        
                        query = query + "})"
                        node= self.execute_query(query, "Creating property node: " + node)
                    except KeyError as missing_key:
                        warning_data = {
                            "domain_model": domain_model.__name__, 
                            "missing_key": str(missing_key), 
                            "node": str(node), 
                            "dict_entry": str(temp_properties_dict[node])
                        }
                        warning_msg = ("A entry in the properties dict in the module '{domain_model}' does not contain a required key." + 
                                        "The missing key is {missing_key} in '{node}': '{dict_entry}'" +
                                        "No node '{node}' can be created! \n").format(**warning_data)
                        print_warning(warning_msg)

        if self.opt_verbose or self.opt_v_verbose:
            print_info("Property Node creation finished!")


    def create_req_property_relations(self, domain_models):
        self._create_property_relations(domain_models, "required_property")

    def create_opt_property_relations(self, domain_models):
        self._create_property_relations(domain_models, "optional_property") 

    #
    # Creates relation creation queries for "optional_property" and "required_property" relations.
    # Nodes need to have a "optional_property" and "required_property" property in order to be considered.
    # relation parameter will be one of ["optional_property" , "required_property"]
    #
    def _create_property_relations(self, domain_models, relation):
        for domain_model in domain_models:
            temp_classes_dict={}
            # for node in domain_model.classes:
            for item in domain_model.classes:
                node = item.keys()[0]
                temp_classes_dict.update(item)
                
                error_data = {
                            "node" : node,
                            "domain_model": domain_model.__name__,
                            "prop_typ": relation
                }
                # checking for "relation"-property, if not found display warning
                try:
                    #if not(temp_classes_dict[node][relation]): raise KeyError(relation)
                    data_type = type(temp_classes_dict[node][relation])

                    # only lists (or strings) are allowed as datatypes of the 'relation' property 
                    if data_type is list:
                        #iterate over all "relation" of this node in the list
                        for prop in temp_classes_dict[node][relation]:
                            query_data = {
                                "node_lower": node.lower(),
                                "node": node,
                                "prop_lower": prop.lower(),
                                "prop": prop,
                                "prop_typ": relation
                            }


                            # Create "MATCH" statement
                            query_match = (
                                "MATCH ({node_lower}:TBox  {{ title: '{node}' }}), ({prop_lower}:TBox {{ title: '{prop}' }})"
                            ).format(**query_data)

                            # Create "CREATE" statement
                            query_create = (
                                "CREATE ({node_lower})-[:{prop_typ}]->({prop_lower})"
                            ).format(**query_data)
                            # Connect "MACTH" and "CREATE" statements
                            query = query_match + " \n " + query_create + "\n"
                            self.execute_query(query, "Creating property relation from {node} to {prop}".format(node = node, prop = prop))
                    elif data_type is str:
                        prop = temp_classes_dict[node][relation]
                        query_data = {
                                "node_lower": node.lower(),
                                "node": node,
                                "prop_lower": prop.lower(),
                                "prop": prop,
                                "prop_typ": relation
                        }

                        # Create "MATCH" statement
                        query_match = ( 
                                "MATCH ({node_lower}:TBox  {{ title: '{node}' }}), ({prop_lower}:TBox {{ title: '{prop}' }})"
                        ).format(**query_data)

                        # Create "CREATE" statement
                        query_create = (
                                "CREATE ({node_lower})-[:{prop_typ}]->({parent_lower})"
                        ).format(**query_data)
                        
                        # Connect "MACTH" and "CREATE" statements
                        query = query_match + " \n " + query_create + "\n"
                        self.execute_query(query, "Creating property relation from {node} to {prop}".format(**query_data))

                    else:
                        warning_msg = ("The '{prop_typ}' of '{node}' in the module '{domain_model}' is neither a list nor a string." +
                                        "Cannot handle other datatypes. No subclass relation for node '{node}' is created!").format(**error_data)
                        print_warning(warning_msg)
                    
                except KeyError as missing_key:
                    print_info(str(missing_key))
                    # info_msg = ("A entry in the properties dict in the module '{domain_model}' does not have a " + str(missing_key) + " property. " + 
                    #             "No {prop_typ} relation for node '{node}' is created!").format(**error_data)
                    # print_info(info_msg)
         
        if self.opt_verbose or self.opt_v_verbose:
            print_info(relation+" relation creation finished!")

    #
    # Create namespace node creation queries.
    # Dynamically take all properties stated for each namespace in the dicts.
    #
    def create_namespaces(self, domain_models):
        for domain_model in domain_models:
            # Check if currently handeled module has a dict called "namespaces"
            # if not skip this module and display warning
            if hasattr(domain_model, "namespaces"):
                temp_namespaces_dict={}
                # Iterate each namespace in namespace dict to dynamically create all namespace querries with properties
                # for namespace in domain_model.namespaces:
                for item in domain_model.namespaces:
                    namespace = item.keys()[0]
                    temp_namespaces_dict.update(item)
                    # KeyError is raised when a requested key is missing.
                    try:
                        query_data = {"namespace": namespace}
                        query = "Create(:namespace {{title: '{namespace}'".format(**query_data)

                        for prop in temp_namespaces_dict[namespace]:
                            property_data = {
                                    "property_name": str(prop),
                                    "property_value": str(temp_namespaces_dict[namespace][prop])
                            }                            
                            if type(temp_namespaces_dict[namespace][prop]) is list:
                                query = query + ",{property_name}:{property_value}".format(**property_data)
                            else:
                                query = query + ",{property_name}:'{property_value}'".format(**property_data)

                        query = query + "})"

                        self.execute_query(query, "Creating namespace node: " + namespace)

                    except KeyError as missing_key:
                        error_data = {
                            "domain_model": domain_model.__name__, 
                            "missing_key": str(missing_key), 
                            "namespace": str(namespace), 
                            "dict_entry": str(temp_namespaces_dict[namespace])
                        }   
                        warning_msg = ("A entry in the 'namespace' dict in module: '{domain_model}' does not contain a required key." + 
                                        "The missing key is {missing_key} in '{namespace} : {dict_entry}'. " + 
                                        "The node {namespace} can not be created!").format(**error_data)
                        print_warning(warning_msg)
            else:
                info_msg = ("No dict called 'namespaces' available in {}. No relations created from this domain-model. " + 
                            "You can safely ignore this, if this is intended.").format(domain_model.__name__)
                print_info(info_msg)

        if self.opt_verbose or self.opt_v_verbose:
            print_info("Namespace nodes created!")

    #
    # Intialize variabls tracking the options
    #
    def __init__(self, opts, args):
        self.neo4j_connection = None
        self.opt_verbose = False
        self.opt_v_verbose = False
        self.opt_output_file = False
        self.arguments = []
        
        #
        # Helper function for loading and displaying helpfile
        #
        def present_helpfile():
            helpfile = open("./helpfile.txt")
            print(helpfile.read())
            helpfile.close()
            return

        # no options or arguments given
        if not opts and not args:
            present_helpfile()
            sys.exit()

        for o, a in opts:

            if "h" in o or "help" in o or o == "":
                present_helpfile()
                sys.exit()

            if "vvv" in o:
                self.opt_verbose = True
                self.opt_v_verbose = True
                print_info("Printing all verbose information available. VERY VERY verbose enabled")
            elif "vv" in o:
                self.opt_v_verbose = True
                print_info("VERY verbose enabled")
            elif "v" in o or "verbose" in o:
                self.opt_verbose = True
                print_info("Vebose enabaled")

            if "db" in o:
                try:
                    # expecting database connection string to be like: protocol://user:pwd@ip:port
                    self.db_url = a.split("@")[1]
                    # check if there is any Protocol specified in the url part of the
                    # argument of the db-connection option.
                    if (self.db_url.__contains__("://") == False): raise DbConnectionError_Protocol     
                    self.db_user = a.split("@")[0].split(":")[0]
                    self.db_pwd = a.split("@")[0].split(":")[1]
                    print_info(str("Connecting to database at: " + self.db_url))

                except (IndexError, DbConnectionError_Protocol) as err:
                        print("WARNING: Database connection parameter not specified correctly.")
                        print("Please enter connection, user and password manually.")
                        self.db_url = raw_input("Enter DB-URL (PROTOKOL://IP:PORT): ")
                        self.db_user = raw_input("Enter DB-User: ")
                        self.db_pwd = raw_input("Enter password: ")

                self.db_url = "{}/db/data".format(self.db_url)

        self.arguments = args



#########################
# Costum Error Handling #
#########################

#
# NoDictionaryError should be raised, if the imported python dict file has an attribut that is expected to be a dictionary but is not. 
#
class NoDictionaryError(ImportError):
    def __init__(self, domain_model, dict_name):
        print("ImportError: '" + dict_name + "' in module " + str(domain_model) + " is not a dictonary")
        sys.exit()

#
# NoDictionaryError should be raised, if the imported python dict file has an attribut that is expected to be a dictionary but is not. 
#
class NoListError(ImportError):
    def __init__(self, domain_model, dict_name):
        print("ImportError: '" + dict_name + "' in module " + str(domain_model) + " is not a list")
        sys.exit()

#
# NoClassesDictError should be raised, if the imported dicht file does not contain a dictionary called "classes"
#
class NoClassesDictError(ImportError):
    def __init__(self, domain_model):
        print("ImportError: No dictionary called 'classes' found in module " + str(domain_model))
        sys.exit()

#
# NoClassesDictError should be raised, if the imported dicht file does not contain a dictionary called "classes"
#
class NoClassesListError(ImportError):
    def __init__(self, domain_model):
        print("ImportError: No list called 'classes' found in module " + str(domain_model))
        sys.exit()

#
# UpperMostLevelError should be raised if the imported dict file does not contain a dictonary that is required at the uppermost level. 
#
class UpperMostLevelError(ImportError):
    def __init__(self, domain_model, dict_name):
        print("ImportError: Dict stated first representing the uppermost level (module: '" + str(domain_model) + "') needs to include a dict called '" + dict_name + "'." )
        sys.exit()

#
# DbConnectioError_Protocol should be raised if no protocol was part of the db-connection string 
#
class DbConnectionError_Protocol(Exception):
    def __init__(self):
        print("No Protocol specified")
        return super(DbConnectionError_Protocol, self).__init__()

class EmptySubClassError(KeyError):
    def __init__(self):
        return super(EmptySubClassError, self).__init__()


#######################
# Execution of import #
#######################

def main():
    global has_warning
    has_warning = False

    try:
        opts, args = getopt.getopt(sys.argv[1:],
                                   "hv",
                                   ["db=", "help", "verbose", "vv", "vvv"])
        # h, help = show helpfile
        # v, verbose = Enable verbose mode
        # vv = Enable very verbose mode
        # db = requires databse connection to be stated

    except getopt.GetoptError as err:
        print(err)
        sys.exit()

    domain_model_creator = DomainModelCreator(opts, args)  # __init__ is run here

    # Import information from dict files
    domain_models = domain_model_creator.import_data_files()

    # Establish Database connection, clear database
    if hasattr(domain_model_creator, "db_url") and hasattr(domain_model_creator, "db_pwd") and hasattr(domain_model_creator, "db_user"):
        try:
            # Set up db connection
            domain_model_creator.setup_db_connection()
            # Call creation scripts
            domain_model_creator.create_nodes(domain_models)
            domain_model_creator.create_relations_subclass(domain_models)
            print 'sas'
            domain_model_creator.create_relations_objectproperty(domain_models)
            domain_model_creator.create_namespaces(domain_models)
            domain_model_creator.create_property_nodes(domain_models)
            domain_model_creator.create_req_property_relations(domain_models)
            domain_model_creator.create_opt_property_relations(domain_models)

        except Exception as e:
            if type(e) == neo4j.exceptions.AuthError:
                print_warning("Could not establish a database connection. URL, password and/or username is inncorrect.")
                sys.exit()
            else:
                raise e

    
    if has_warning == True and domain_model_creator.neo4j_connection != None:
        domain_model_creator.execute_query("MATCH (n) DETACH DELETE n", "Clearing Database due to critical error".upper())
        print("// Finished with a critical error during importing or parsing the files. \n" +
            "// The db was cleared, since some entities were missing some required information. \n" + 
            "// Plaese see displayed warnings for details. \n" +
            "// Please fix these warnings and rerun the script to load the db. \n")
    elif has_warning == True:
        print("// Finished with a critical any critical error during importing or parsing the files. \n" +
            "// However, some issues with the data were identified. \n" + 
            "// Plaese see displayed warnings for details. \n" +
            "// Please fix these warnings before attempting to load the db. \n")
    else: 
        print_info("FINISHED SUCCESSFULLY")

#
# Helper function for printing cypher compatible success info
#
def print_info(msg):
    print("\n//INFO: {} \n".format(msg))

#
# Helper function for printing cyhper compatible warnings
# Sets also warning flag for displaying master warning after script has finished
#
def print_warning(msg):
    global has_warning
    has_warning = True
    print("\n//#### WARNING ####\n//{}\n".format(msg))


if __name__ == "__main__":
    # execute only if run as a script
    main()


