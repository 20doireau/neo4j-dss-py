import dataiku
from subprocess import Popen, PIPE

def export_dataset(dataset=None, output_file=None, format="tsv-excel-noheader"):
    ds = dataiku.Dataset(dataset)
    with open(output_file, "w") as o:
        with ds.raw_formatted_data(format=format) as i:
            while True:
                chunk = i.read(32000)
            if len(chunk) == 0:
                break
            o.write(chunk)
    
def copy_to_server