This is a plugin to load python dicts representing a domain model into a Neo4j graph

- Scripts handling the import of domain model information from xlxs files or python dictionary files to a neo4j database

## Requirements

- Python2.7
- Extracting data from Excel
  - `xlrd` Version 1.2.0 -> `pip install xlrd`
- Creting cypher queries:
  - `py2neo` Version 4.1.3 -> `pip install py2neo==4.1.3` (Windows) or `pip install 'py2neo==4.1.3'` (Linux)
- *There have been some issues with different version of pip-packages that are installed with py2neo. It might be necessary to revert to an earlier version*


## XLXS reader

- Run `xlsxreader.py`
- Takes path of xlsx file from the argument 
- This script creates python files containting dicts with the data for the "upper" level and the "simutool" from the input excelfile . I
- These files are saved to `.` where python was run.


## Neo4j Graph Populator

### The python-files containing the information for the domain-models

- They need to have the following structure:

``` python
classes =  [ { node: {property: ... }, ... ]
relations = [ { relation: {property: ... }, ... ]
namespaces = [ { namespace: {property: ... }, ... ]
```

- `classes` is always required.
- `relations` and `namespaces` are optional.
- `relations` holds all object-property relations of this domain-model.
- `namespaces` holds information for the namespaces added by this domain-model/on this level. Therefore, the uppermost domain-model file needs to include a namespaces dict in order to introduce namespaces at all.

### Creating cypher queries

- Run `import_domain_model.py` with the python files storing information about each level as arguments to create the cypher-queries
- The python file in the first argument is expected to contain the information of the uppermost level. This means it requires at least dicts called `classes` and `namespaces`
- This script creates cypher queries for creating the class and namespace nodes and the relations between classes (subclass relations as well as object-property relations).
- It is possible to state a database connection via the `--db` flag. Following syntax is required: `user:pwd@ip:port`. If the `--db` flag is set but the given parameter does not match the expected structure, you will be asked to entered `ip:port`, `user` and `pwd` manually. The stated database is than erased and filled with the information form the python-dict-files in the arguments.
- If no `--db` flag is set the cypher queries will just be printed to std-out.
- All available options and parameters can be seen using the `--help` or `-h` option. The help option will provide the `helpfile.txt`.
- **Caution:** The script always erases the database completely after connecting. This means also entries that are not being altered by this script are lost. Also errors while creating and running the cyphers will erase the databse in order to leave the databas in a consistent state (empty)
- Erros during the import will just exit before connection to the databse  and do therefore not erase the database


