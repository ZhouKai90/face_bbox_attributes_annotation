face_bbox_attributes_annotation
========

Tools for face bbox and attributes annotate.

It is written in Python and uses Qt for its graphical interface.

Annotations are saved as XML files in PASCAL VOC format.

Baseline: https://github.com/tigerzhaoyue/Face_Boundingbox_Attributes 

Installation
------------------

Build from source

Linux/Ubuntu requires at least Python3.6

Ubuntu Linux

Python 3 + Qt5
   ` sudo apt-get install pyqt5-dev-tools
  sudo pip3 install lxml
  make qt5py3
  python3 labelImg.py`


Steps

1. Build and launch using the instructions above.
2. Click 'Change default saved annotation folder' in Menu/File
3. Click 'Open Dir'
4. Click 'Create RectBox'
5. Click and release left mouse to select a square region to annotate the square
   box
6. You can use right mouse to drag the square box to copy or move it

The annotation and atttributes of faces will be saved to the folder you specify.

You can refer to the below hotkeys to speed up your workflow.





|          |                                          |
| -------- | ---------------------------------------- |
| Ctrl + u | Load all of the images from a directory  |
| Ctrl + r | Change the default annotation target dir |
| Ctrl + d | Copy the current label and rect box      |
| Space    | Flag the current image as verified       |
| Ctrl++   | Zoom in                                  |
| Ctrl--   | Zoom out                                 |
| ↑        | Create a rect box                        |
| ↓        | Save                                     |
| ←        | Previous image                           |
| →        | Next image                               |