from dataiku.customwebapp import get_plugin_config, get_webapp_config

# Access the parameters that end-users filled in using webapp config
# For example, for a parameter called "input_dataset"
# input_dataset = get_webapp_config()["input_dataset"]

import dataiku
import pandas as pd
from flask import request
import json
from py2neo import Graph
import re


# Example:
# As the Python webapp backend is a Flask app, refer to the Flask
# documentation for more information about how to adapt this
# example to your needs.
# From JavaScript, you can access the defined endpoints using
# getWebAppBackendUrl('first_api_call')

connection_info = get_webapp_config().get('connection_info')
print("connection_info: ", connection_info)
try:
    graph = Graph(connection_info.get("neo4j_uri"), auth=(connection_info.get("neo4j_username"), connection_info.get("neo4j_password")))
except Exception:
    raise ValueError("Fail to connect to neo4j server !")


class GraphError(Exception):
    """Base class for other exceptions"""
    pass

# graph = Graph("bolt://localhost:7687", auth=("neo4j", "test"))


@app.route('/draw_graph')
def draw_graph():
    try:
        print("starting backend function !")

        config = json.loads(request.args.get('config', None))

        print('config: ', config)

        query_limit = config['query_limit']
        relations = config['relations']
        node_params = config['node_params']
        rel_params = config['rel_params']

        relations_list = []
        unique_nodes_labels = set()
        unique_edges_types = set()
        for i, rel in enumerate(relations):
            if rel['source'] not in unique_nodes_labels:
                unique_nodes_labels.add(rel['source'])
            if rel['target'] not in unique_nodes_labels:
                unique_nodes_labels.add(rel['target'])
            if rel['relation'] not in unique_edges_types:
                unique_edges_types.add(rel['relation'])

        print("relations: ", relations)
        query, unique_nodes_id, unique_edges_id = multiple_relation_query(relations)
        query += "\nLIMIT {}".format(query_limit)

        print("query: ", query)

        try:
            data = graph.run(query)
        except Exception as e:
            raise GraphError("Graph error: {}".format(e))


        nodes_list = []
        edges_list = []
        seen_nodes = set()

        compt = 0    # check if query result is empty
        for row in data:
            compt += 1
            row_dict = dict(row)

            # add nodes to nodes_list
            for n in unique_nodes_id:
                node = row_dict[n]
                node_id = row_dict["{}_id".format(n)]

                # can sometimes have multiple labels (get first label in list that is in node_params)
                node_labels = list(node.labels)
                if len(node_labels) == 1:
                    node_label = node_labels[0]
                else:
                    node_label = next((label for label in node_labels if label in unique_nodes_labels), None)
                    if node_label is None:
                        raise ValueError("Cypher error with a node with multiple labels {}".format(node_labels))

                if node_id not in seen_nodes:
                    seen_nodes.add(node_id)
                    node_info = get_node_info(node, node_id, node_params.get(node_label, None))
                    nodes_list.append(node_info)

            # add edges to edges_list
            for e in unique_edges_id:
                rel = row_dict[e]
                src_id = rel.start_node.identity
                tgt_id = rel.end_node.identity
                rel_type = type(rel).__name__

                rel_info = get_rel_info(rel, src_id, tgt_id, rel_params.get(rel_type, None))
                edges_list.append(rel_info)

        if compt == 0:
            raise GraphError("Graph error: {}".format("Cypher query result is empty !"))

        results = {"nodes": nodes_list, "edges": edges_list}
    #     print("results: ", results)

        return json.dumps(results)

    except GraphError as ge:
#         logger.error(traceback.format_exc())
        return str(ge), 505
    except Exception as e:
#         logger.error(traceback.format_exc())
        return "Backend error: {}".format(str(e)), 500


def get_node_info(node, node_id, node_params):
    info = {"id": node_id}
    properties = dict(node)
    if node_params is not None:
        info["label"] = str_or_none(properties.get(node_params["caption"], None))
        try: 
            info["value"] = int(properties.get(node_params["size"], 0))
        except Exception:
            pass
        info["group"] = properties.get(node_params["color"], None)
        info["shape"] = node_params["shape"]
        
    info["title"] = dict_to_nice_str(properties)
    
    return info

#shapes label inside: ellipse, circle, database, box, text
#shapes label outside: image, circularImage, diamond, dot, star, triangle, triangleDown, hexagon, square and icon.


def get_rel_info(rel, src_id, tgt_id, rel_params):
    info = {"from": src_id, "to": tgt_id}
    properties = dict(rel)
    if rel_params is not None:
        info["label"] = str_or_none(properties.get(rel_params["caption"], None))
        try:
            info["value"] = int(properties.get(rel_params["width"], 0))
        except Exception:
            pass
        
    info["title"] = dict_to_nice_str(properties)
    return info


def multiple_relation_query(relations):
    match_list = []
    return_list = []
    unique_nodes_id = set()
    unique_edges_id = set()
    
    for index, rel in enumerate(relations):
        match_list += ["({0}:{1})-[{2}:{3}]->({4}:{5})".format(rel['src_id'], rel['source'], rel['rel_id'], rel['relation'], rel['tgt_id'], rel['target'])]
        
        if rel['src_id'] not in unique_nodes_id:
            unique_nodes_id.add(rel['src_id'])
        if rel['tgt_id'] not in unique_nodes_id:
            unique_nodes_id.add(rel['tgt_id'])
#         if rel[2] not in unique_edges:
        unique_edges_id.add(rel['rel_id'])
    
    for node in unique_nodes_id:
        return_list += ["{}".format(node), "id({0}) AS {0}_id".format(node)]
    for edge in unique_edges_id:
        return_list += [edge]
    
    match_statement = "MATCH\n" + ",\n".join(match_list)
    return_statement = "\nRETURN\n" + ", ".join(return_list)
    
    return match_statement + return_statement, unique_nodes_id, unique_edges_id




@app.route('/get_node_labels')
def get_node_labels():
    query = "CALL db.labels()"
    data = graph.run(query)
    node_labels = []
    for row in data:
        node_labels += [row[0]]
    return json.dumps({"node_labels": node_labels})

@app.route('/get_relation_types')
def get_relation_types():
    query = "call db.schema"
    relationships = graph.run(query).data()[0]['relationships']
    relation_types = set()
    for rel in relationships:
        relation_types.add(type(rel).__name__)
    return json.dumps({"relation_types": list(relation_types)})




@app.route('/get_other_labels')
def get_other_labels():
    
    current_label = request.args.get('current_label', None)
    rel_type = request.args.get('rel_type', None)
    other = request.args.get('other', None)
    
    query = "call db.schema"
    dic = graph.run(query).data()[0]
    relationships = dic['relationships']
    other_labels = set()
    for rel in relationships:
        if other == 'Target':
            if current_label == rel.start_node['name'] and rel_type == type(rel).__name__:
                other_labels.add(rel.end_node['name'])
        elif other == 'Source':
            if current_label == rel.end_node['name'] and rel_type == type(rel).__name__:
                other_labels.add(rel.start_node['name'])
                
    print("list(other_labels): ", list(other_labels))
    return json.dumps({"other_labels": list(other_labels)})



@app.route('/get_target_labels')
def get_target_labels():
    
    source_label = request.args.get('source_label', None)
    rel_type = request.args.get('rel_type', None)
    
    query = "call db.schema"
    dic = graph.run(query).data()[0]
    relationships = dic['relationships']
    target_labels = set()
    for rel in relationships:
        if source_label == rel.start_node['name'] and rel_type == type(rel).__name__:
            target_labels.add(rel.end_node['name'])
    print("list(target_labels): ", list(target_labels))
    return json.dumps({"target_labels": list(target_labels)})


@app.route('/get_relationship_types')
def get_relationship_types():
    """
    return a list of relationship types related to the source (current==Source) or target (current==Target) node label
    """    
    current_label = request.args.get('current_label', None)
    current = request.args.get('current', None)
    
    query = "call db.schema"
    dic = graph.run(query).data()[0]
    relationships = dic['relationships']
    rel_types = set()
    
    print("dic: ", dic)
    print("current_label: ", current_label)
    for rel in relationships:
        if current == 'Source':
            if current_label == rel.start_node['name']:
                rel_types.add(type(rel).__name__)
        elif current == 'Target':
            if current_label == rel.end_node['name']:
                rel_types.add(type(rel).__name__)
    print("rel_types: ", rel_types)
    # TODO check if no node labels at all
    return json.dumps({"relationship_types": list(rel_types)})
    

@app.route('/get_node_properties')
def get_node_properties():
    node_label = request.args.get('node_label', None)
    numerical = True if request.args.get('numerical', False)=='true' else False
    
    query = "call db.schema.nodeTypeProperties"
    results = graph.run(query).data()
    node_properties = []
    for row in results:
        if node_label == row['nodeLabels'][0] and row["propertyName"] is not None:
            if numerical:
                # TODO maybe allow for 'Double' type as well
                if row["propertyTypes"] is not None:
                    if 'Long' in row["propertyTypes"] or 'Double' in row["propertyTypes"]:
                        node_properties += [row["propertyName"]]
            else:
                node_properties += [row["propertyName"]]
    return json.dumps({"node_properties": node_properties})


@app.route('/get_rel_properties')
def get_rel_properties():
    rel_type = request.args.get('rel_type', None)
    numerical = True if request.args.get('numerical', False)=='true' else False
    
    query = "call db.schema.relTypeProperties"
    results = graph.run(query)
    rel_properties = []
    for row in results:
        if rel_type == row['relType'][2:-1] and row["propertyName"] is not None:
            if numerical:
                # TODO maybe allow for 'Double' type as well
                if row["propertyTypes"] is not None:
                    if 'Long' in row["propertyTypes"] or 'Double' in row["propertyTypes"]:
                        rel_properties += [row["propertyName"]]
            else:
                rel_properties += [row["propertyName"]]
    return json.dumps({"rel_properties": rel_properties})


def dict_to_nice_str(dic):
    return ", ".join(["{}: {}".format(key, value) for key, value in dic.items()])

def str_or_none(value):
    return str(value) if value is not None else None


@app.route('/draw_subgraph')
def draw_subgraph():
    node_label = request.args.get('node_label', None)
    rel_type = request.args.get('rel_type', None)
    node_caption = request.args.get('node_caption', None)
    node_color = request.args.get('node_color', None)
    node_size = request.args.get('node_size', None)
    rel_caption = request.args.get('rel_caption', None)
    rel_size = request.args.get('rel_size', None)
    query_limit = request.args.get('query_limit', 0)
    selected_node_id = int(request.args.get('selected_node_id', None))
    
    query = """
    MATCH (n:{0})
    WHERE id(n) = {1}
    CALL apoc.path.subgraphAll(n, {{
        relationshipFilter: '{2}',
        labelFilter: '+{0}',
        minLevel: 0,
        maxLevel: 2,
        limit: {3}
    }})
    YIELD nodes, relationships
    RETURN nodes, relationships
    """.format(node_label, selected_node_id, rel_type, query_limit)

    print("query subgraph: ", query)
    
    params = {
        "node_label": node_label,
        "rel_type": rel_type,
        "node_caption": node_caption,
        "node_color": node_color,
        "node_size": node_size,
        "rel_caption": rel_caption,
        "rel_size": rel_size,
        "query_limit": query_limit
    }    

    data = graph.run(query).data()

    nodes_data = data[0]["nodes"]
    edges_data = data[0]["relationships"]

    nodes = []
    edges = []

    for node in nodes_data:
        node_id = node.identity
        node_info = get_node_info(node, node_id, params)
        if node_id == selected_node_id:
            node_info["physics"] = False
            print(node_info)
        nodes.append(node_info)

    for rel in edges_data:
        rel_info = get_rel_info(rel, rel.start_node.identity, rel.end_node.identity, params)
        edges.append(rel_info)

    results = {"nodes": nodes, "edges": edges}

    return json.dumps(results)

