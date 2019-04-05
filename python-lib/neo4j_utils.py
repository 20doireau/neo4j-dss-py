import sys
import logging
import dataiku
from subprocess import Popen, PIPE

logger = logging.getLogger()

def export_dataset(dataset=None, output_file=None, format="tsv-excel-noheader"):
    '''
    This function exports a Dataiku Dataset to CSV with no 
    need to go through a Pandas dataframe first
    '''
    logger.info("[+] Starting file export...")
    ds = dataiku.Dataset(dataset)
    with open(output_file, "w") as o:
        with ds.raw_formatted_data(format=format) as i:
            while True:
                chunk = i.read(32000)
                if len(chunk) == 0:
                    break
                o.write(chunk)
    logger.info("[+] Export done.")


def scp_nopassword_to_server(file_to_copy=None, sshuser=None, sshhost=None, sshpath=None):
    '''
    This function copies a file to a remote server using SCP. 
    It requires a password-less access (i.e SSH public key is available)
    '''
    logger.info("[+] Copying file to remote server...")
    p = Popen(
        ["scp", file_to_copy, "{}@{}:{}".format(sshuser, sshhost, sshpath)], 
        stdin=PIPE, stdout=PIPE, stderr=PIPE
    )
    out, err = p.communicate()
    logger.info("[+] Copying file complete.")
    return out, err


def build_node_schema(node_label=None, dataset=None):
    '''
    This specific function generates the "schema" for a 
    node from a Dataiku Dataset
    '''
    ds = dataiku.Dataset(dataset)
    schema = ''
    schema = schema + ':{}'.format(node_label)
    schema = schema + ' {' + '\n'
    c = ',\n'.join( ["  {}: line[{}]".format(r["name"], i) for i, r in enumerate(ds.read_schema())] )
    schema = schema + c
    schema = schema + '\n' + '}'
    logger.info("[+] Schema generation complete for node {}.".format(node_label))
    return schema


def delete_nodes_with_label(graph=None, node_label=None):
    '''
    Simple helper to delete all nodes with a given label within
    a Neo4j graph
    '''
    q = """
      MATCH (n:%s)
      DETACH DELETE n
    """ % (node_label)
    logger.info("[+] Starting deleting existing nodes with label {}...".format(node_label))
    try:
        r = graph.run(q)
        logger.info("[+] Existing nodes with label {} deleted.".format(node_label))
    except Exception, e:
        logger.error("[-] Issue while deleting nodes with label {}".format(node_label))
        logger.error("[-] {}".format( str(e) ))
        sys.exit(1)
    

def create_nodes_from_csv(graph=None, csv=None, schema=None):
    '''
    Actually creates Neo4j nodes from a Dataiku Dataset 
    '''
    q = """
      LOAD CSV FROM 'file:///%s' AS line FIELDTERMINATOR '\t'
      CREATE (%s)
    """ % (csv, schema)
    logger.info("[+] Starting CSV import into Neo4j ...")
    try:
        r = graph.run(q)
        logger.info("[+] CSV import complete.")
    except Exception, e:
        msg = "[-] Issue while loading CSV file"
        msg = msg + "[-] {}".format( str(e) )
        raise Exception(msg)