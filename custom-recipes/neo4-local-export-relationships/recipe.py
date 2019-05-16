import os
import logging
import dataiku
from py2neo import Graph
from neo4j_utils import *
from subprocess import Popen, PIPE
from dataiku.customrecipe import *
from logging import FileHandler

#==============================================================================
# PLUGIN SETTINGS
#==============================================================================

# I/O settings
INPUT_DATASET_NAME                = get_input_names_for_role('inputDataset')[0]
OUTPUT_FOLDER_NAME                = get_output_names_for_role('outputFolder')[0]

# Plugin settings
NEO4J_URI                          = get_plugin_config().get("neo4jUri", None)
NEO4J_USERNAME                     = get_plugin_config().get("neo4jUsername", None)
NEO4J_PASSWORD                     = get_plugin_config().get("neo4jPassword", None)

# Recipe settings
GRAPH_NODES_FROM_LABEL             = get_recipe_config().get('graphNodesFromLabel', None)
GRAPH_NODES_FROM_KEY               = get_recipe_config().get('graphNodesFromKey', None)
GRAPH_NODES_TO_LABEL               = get_recipe_config().get('graphNodesToLabel', None)
GRAPH_NODES_TO_KEY                 = get_recipe_config().get('graphNodesToKey', None)
GRAPH_RELATIONSHIPS_FROM_KEY       = get_recipe_config().get('graphRelationshipsFromKey', None)
GRAPH_RELATIONSHIPS_TO_KEY         = get_recipe_config().get('graphRelationshipsToKey', None)
GRAPH_RELATIONSHIPS_VERB           = get_recipe_config().get('graphRelationshipsVerb', None)
GRAPH_RELATIONSHIPS_SET_PROPERTIES = get_recipe_config().get('graphRelationshipsSetProperties', False)
GRAPH_RELATIONSHIPS_DELETE         = get_recipe_config().get('graphRelationshipsDelete', True)
NEO4J_IMPORT_DIR                   = get_recipe_config().get('neo4jImportDir', None)

EXPORT_FILE_NAME      = 'export.csv'


#==============================================================================
# LOGGING SETTINGS
#==============================================================================

logger = logging.getLogger()
logger.setLevel(logging.INFO)
formatter = logging.Formatter('%(asctime)s :: %(levelname)s :: %(message)s')

export_folder = dataiku.Folder(OUTPUT_FOLDER_NAME).get_path()
export_log = os.path.join(export_folder, 'export.log')
file_handler = FileHandler(export_log, 'w')
file_handler.setFormatter(formatter)
logger.addHandler(file_handler)

logger.info("*"*80)
logger.info("* NEO4J EXPORT PROCESS START")
logger.info("*"*80)


#==============================================================================
# EXPORTING TO CSV
#==============================================================================

export_file = os.path.join(export_folder, EXPORT_FILE_NAME)
export_dataset(dataset=INPUT_DATASET_NAME, output_file=export_file)


#==============================================================================
# COPYING TO NEO4J IMPORT FOLDER
#==============================================================================

logger.info("[+] Making file available to Neo4j...")
outfile = os.path.join(NEO4J_IMPORT_DIR, EXPORT_FILE_NAME)
shutil.copyfile(export_file, outfile)
logger.info("[+] Done.")
    

#==============================================================================
# LOADING DATA INTTO NEO4J
#==============================================================================

# Connect to Neo4j
uri = NEO4J_URI
graph = Graph(uri, auth=("{}".format(NEO4J_USERNAME), "{}".format(NEO4J_PASSWORD)))

# Add constraints and unique indices to the original nodes
logger.info(  "[+] Creating constraints on nodes...")
r = graph.run("CREATE CONSTRAINT ON (n:%s) ASSERT n.%s IS UNIQUE" % (GRAPH_NODES_FROM_LABEL, GRAPH_NODES_FROM_KEY))
r = graph.run("CREATE CONSTRAINT ON (n:%s) ASSERT n.%s IS UNIQUE" % (GRAPH_NODES_TO_LABEL, GRAPH_NODES_TO_KEY))
logger.info(  "[+] Done creating constraints on nodes.")

# Clean data if needed
if GRAPH_RELATIONSHIPS_DELETE:
    delete_relationships(graph=graph, nodes_a_label=GRAPH_NODES_FROM_LABEL, nodes_b_label=GRAPH_NODES_TO_LABEL, relationships_verb=GRAPH_RELATIONSHIPS_VERB)

# Creating schema
(schema, attributes) = build_relationships_schema(
    dataset=INPUT_DATASET_NAME, 
    key_a=GRAPH_NODES_FROM_KEY, 
    key_b=GRAPH_NODES_TO_KEY, 
    set_properties=GRAPH_RELATIONSHIPS_SET_PROPERTIES
)

# Actually load the data
create_relationships_from_csv(graph=graph, csv=EXPORT_FILE_NAME, schema=schema,
                              graph_nodes_left_label=GRAPH_NODES_FROM_LABEL, graph_nodes_left_key=GRAPH_NODES_FROM_KEY, graph_relationships_left_key=GRAPH_RELATIONSHIPS_FROM_KEY,
                              graph_nodes_right_label=GRAPH_NODES_TO_LABEL, graph_nodes_right_key=GRAPH_NODES_TO_KEY, graph_relationships_right_key=GRAPH_RELATIONSHIPS_TO_KEY,
                              graph_relationships_verb=GRAPH_RELATIONSHIPS_VERB, graph_relationships_attributes=attributes)

    
#==============================================================================
# FINAL CLEANUP
#==============================================================================

# Remote file
os.remove(outfile)

# Local file
os.remove(export_file)

logger.info("*"*80)
logger.info("* NEO4J EXPORT PROCESS END")
logger.info("*"*80)