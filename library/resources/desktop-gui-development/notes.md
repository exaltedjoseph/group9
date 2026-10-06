# Desktop GUI Development

## Widgets and layouts
A window holds widgets: labels, buttons, fields, and lists. Layouts place them so the window can resize. Stack related widgets vertically or horizontally instead of pinning them to pixels.

## Events and callbacks
The user clicks, types, or closes a window. The toolkit calls your function. Keep the callback short and hand the real work to ordinary Python functions so it stays testable.

```python
def on_save():
    library.add_resource(title_field.text())

save_button.clicked.connect(on_save)
```

## Packaging apps
A desktop app is more than a script. Freeze the entry point, include data files, and test the built app on a clean machine. Settings and user data stay outside the install folder.
