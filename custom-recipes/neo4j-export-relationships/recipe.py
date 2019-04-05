import os
import logging
import dataiku
import pandas as pd
from py2neo import Graph
from subprocess import Popen, PIPE
from dataiku.customrecipe import *
from logging import FileHandler

#==============================================================================
# PLUGIN SETTINGS
#==============================================================================

# I/O settings
INPUT_DATASET_NAME                = get_input_names_for_role('input-dataset')[0]
OUTPUT_FOLDER_NAME                = get_output_names_for_role('output-folder')[0]

# Recipe settings
GRAPH_NODES_FROM_LABEL            = get_recipe_config().get('graph-nodes-from-label', None)
GRAPH_NODES_FROM_KEY              = get_recipe_config().get('graph-nodes-from-key', None)
GRAPH_RELATIONSHIPS_FROM_KEY      = get_recipe_config().get('graph-relationships-from-key', None)
GRAPH_NODES_TO_LABEL              = get_recipe_config().get('graph-nodes-to-label', None)
GRAPH_NODES_TO_KEY                = get_recipe_config().get('graph-nodes-to-key', None)
GRAPH_RELATIONSHIPS_TO_KEY        = get_recipe_config().get('graph-relationships-to-key', None)
GRAPH_RELATIONSHIP_VERB           = get_recipe_config().get('graph-relationship-verb', None)
GRAPH_RELATIONSHIP_SET_PROPERTIES = get_recipe_config().get('graph-relationship-set-properties', None)
NEO4J_URI                         = get_recipe_config().get('neo4j-uri', None)
NEO4J_USER                        = get_recipe_config().get('neo4j-user', None)
NEO4J_PASSWORD                    = get_recipe_config().get('neo4j-password', None)
SSH_HOST                          = get_recipe_config().get('ssh-host', None)
SSH_USER                          = get_recipe_config().get('ssh-user', None)
SSH_IMPORT_DIRECTORY              = get_recipe_config().get('ssh-import-directory', None)



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

logging.info("[+] Reading dataset as dataframe...")
ds = dataiku.Dataset(INPUT_DATASET_NAME)
df = ds.get_dataframe()
logger.info("[+] Read dataset with {} rows and {} columns\n".format(df.shape[0], df.shape[1]))

logger.info("[+] Exporting input dataframe to CSV...")
df.to_csv(path_or_buf=os.path.join(out_folder, 'export.csv'), sep="|",header=False, index=False)
logger.info("[+] Exported to CSV\n")


#==============================================================================
# COPYING TO NEO4J SERVER
#==============================================================================

logger.info("[+] Copying file to Neo4j server...")

p = Popen(
    [
        "scp", 
        os.path.join(out_folder, 'export.csv'), 
        "{}@{}:{}".format(SSH_USER, SSH_HOST, SSH_IMPORT_DIRECTORY)
    ], stdin=PIPE, stdout=PIPE, stderr=PIPE
)

out, err = p.communicate()

if err == '':
    logger.info("[+] Copied file to Neo4j server\n")
else:
    logger.error("[-] Issue while copying CSV file to Neo4j server")
    logger.error("[-] {}\n".format(err))
    
    

#==============================================================================
# LOADING DATA INTTO NEO4J
#==============================================================================

# Connect to Neo4j
uri = NEO4J_URI
graph = Graph(uri, auth=("{}".format(NEO4J_USER), "{}".format(NEO4J_PASSWORD)))

# Add constraints and unique indices to the original nodes
r = graph.run("CREATE CONSTRAINT ON (n:%s) ASSERT n.%s IS UNIQUE" % (GRAPH_NODES_FROM_LABEL, GRAPH_NODES_FROM_KEY))
r = graph.run("CREATE CONSTRAINT ON (n:%s) ASSERT n.%s IS UNIQUE" % (GRAPH_NODES_TO_LABEL, GRAPH_NODES_TO_KEY))


# Creating schema
schema = ', '.join( ['line[{}] AS {}'.format(i, column) for i, column in enumerate(df.columns)] )
logger.info("[+] Built Neo4j output schema")
#logger.info("[+]\n{}\n".format(schema))


       
# Actually load the data
q = """
  USING PERIODIC COMMIT
  LOAD CSV FROM 'file:///%s' AS line FIELDTERMINATOR '|'
  WITH %s
  MATCH (f:%s {%s: %s})
  MATCH (t:%s {%s: %s})
  MERGE (f)-[rel:%s]->(t)
""" % (
    'export.csv', 
    schema, 
    GRAPH_NODES_FROM_LABEL, GRAPH_NODES_FROM_KEY, GRAPH_RELATIONSHIPS_FROM_KEY,
    GRAPH_NODES_TO_LABEL, GRAPH_NODES_TO_KEY, GRAPH_RELATIONSHIPS_TO_KEY,
    GRAPH_RELATIONSHIP_VERB
)

logger.info("[+] Loading CSV file into Neo4j using query:...")
logger.info("[+] %s" % (q))
try:
    r = graph.run(q)
    logger.info("[+] Loading complete")
    logger.info(r.stats())
except Exception, e:
    logger.error("[-] Issue while loading CSV")
    logger.error("[-] {}\n".format(str(e)))
    
    
#==============================================================================
# FINAL CLEANUP
#==============================================================================

# Remote file
p = Popen(
    ["ssh", "{}@{}".format(SSH_USER, SSH_HOST), "rm -rf", "{}/export.csv".format(SSH_IMPORT_DIRECTORY)], 
    stdin=PIPE, stdout=PIPE, stderr=PIPE
)
out, err = p.communicate()

# Local file
os.remove( os.path.join(out_folder, 'export.csv') )
