# Data Analysis

## NumPy
NumPy arrays store numbers in a fixed type and run calculations across the whole array.

```python
import numpy as np
scores = np.array([71, 84, 90, 66])
print(scores.mean(), scores.max())
```

## pandas
A `DataFrame` is a table with named columns. Filter rows, pick columns, and group.

```python
import pandas as pd
df = pd.DataFrame({
    "module": ["git", "git", "sql"],
    "score": [80, 95, 88],
})
print(df[df["module"] == "git"]["score"].mean())
```

## Data visualization
A chart should answer one question. A bar chart compares modules. A line chart shows a score across weeks. Label the axes and the units before you decorate anything.
