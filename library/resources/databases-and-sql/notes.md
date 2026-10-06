# Databases and SQL

## Relational design
A table is a set of rows. Each row is one thing. A primary key identifies the row. A foreign key points at a row in another table.

Modules have many resources. `resources.module_id` refers to `modules.id`.

## SQL queries
`SELECT` reads rows. `WHERE` filters. `JOIN` combines tables. `ORDER BY` sorts.

```sql
SELECT title, module_id
FROM resources
WHERE kind = 'notes'
ORDER BY title;
```

## Python and SQLite
The `sqlite3` module opens a file database. Use parameters instead of building SQL with string concatenation.

```python
import sqlite3
con = sqlite3.connect("library.db")
rows = con.execute("SELECT title FROM resources WHERE module_id = ?", ("databases-and-sql",))
```
