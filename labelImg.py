#!/usr/bin/env python
# -*- coding: utf-8 -*-
import codecs
import os.path
import re
import sys
import subprocess

from functools import partial
from collections import defaultdict

try:
    from PyQt5.QtGui import *
    from PyQt5.QtCore import *
    from PyQt5.QtWidgets import *
except ImportError:
    # needed for py3+qt4
    # Ref:
    # http://pyqt.sourceforge.net/Docs/PyQt4/incompatible_apis.html
    # http://stackoverflow.com/questions/21217399/pyqt4-qtcore-qvariant-object-instead-of-a-string
    if sys.version_info.major >= 3:
        import sip
        sip.setapi('QVariant', 2)
    from PyQt4.QtGui import *
    from PyQt4.QtCore import *

import resources
# Add internal libs
from libs.constants import *
from libs.lib import struct, newAction, newIcon, addActions, fmtShortcut
from libs.settings import Settings
from libs.shape import Shape, DEFAULT_LINE_COLOR, DEFAULT_FILL_COLOR
from libs.canvas import Canvas
from libs.zoomWidget import ZoomWidget
from libs.labelDialog import LabelDialog
from libs.colorDialog import ColorDialog
from libs.labelFile import LabelFile, LabelFileError
from libs.toolBar import ToolBar
from libs.pascal_voc_io import PascalVocReader
from libs.pascal_voc_io import XML_EXT
from libs.ustr import ustr

__appname__ = 'Face Attribute'

# Utility functions and classes.


def have_qstring():
    '''p3/qt5 get rid of QString wrapper as py3 has native unicode str type'''
    return not (sys.version_info.major >= 3 or QT_VERSION_STR.startswith('5.'))


def util_qt_strlistclass():
    return QStringList if have_qstring() else list


class WindowMixin(object):

    def menu(self, title, actions=None):
        menu = self.menuBar().addMenu(title)
        if actions:
            addActions(menu, actions)
        return menu

    def toolbar(self, title, actions=None):
        toolbar = ToolBar(title)
        toolbar.setObjectName(u'%sToolBar' % title)
        # toolbar.setOrientation(Qt.Vertical)
        toolbar.setToolButtonStyle(Qt.ToolButtonTextUnderIcon)
        if actions:
            addActions(toolbar, actions)
        self.addToolBar(Qt.LeftToolBarArea, toolbar)
        return toolbar


# PyQt5: TypeError: unhashable type: 'QListWidgetItem'
class HashableQListWidgetItem(QListWidgetItem):

    def __init__(self, *args):
        super(HashableQListWidgetItem, self).__init__(*args)

    def __hash__(self):
        return hash(id(self))


class MainWindow(QMainWindow, WindowMixin):
    FIT_WINDOW, FIT_WIDTH, MANUAL_ZOOM = list(range(3))

    def __init__(self, defaultFilename=None, defaultPrefdefClassFile=None):
        super(MainWindow, self).__init__()
        self.setWindowTitle(__appname__)
        # Save as Pascal voc xml
        self.defaultSaveDir = None
        self.usingPascalVocFormat = True
        # For loading all image under a directory
        self.mImgList = []
        self.dirname = None
        self.labelHist = []
        self.lastOpenDir = None

        # Whether we need to save or not.
        self.dirty = False

        self._noSelectionSlot = False
        self._beginner = True
        self.screencastViewer = "firefox"
        self.screencast = "https://youtu.be/p0nR2YsCY_U"

        # Main widgets and related state.
        self.labelDialog = LabelDialog(parent=self, listItem=self.labelHist)
        self.ageDialog = LabelDialog(parent=self, listItem=['0','10','20','30','40','50','60','70','80','90'])
        self.itemsToShapes = {}
        self.shapesToItems = {}
        self.prevLabelText = ''

        listLayout = QGridLayout()
        listLayout.setContentsMargins(0, 0, 0, 0)

        # Create a widget for using default label

        row_loc = 0
        self.useDefaultLabelCheckbox = QCheckBox(u'')
        self.useDefaultLabelCheckbox.setChecked(False)
        self.defaultLabelTextLine = QLineEdit()
        useDefaultLabelQHBoxLayout = QHBoxLayout()
        #useDefaultLabelQHBoxLayout.addWidget(self.useDefaultLabelCheckbox)
        #useDefaultLabelQHBoxLayout.addWidget(self.defaultLabelTextLine)
        useDefaultLabelContainer = QWidget()
        useDefaultLabelContainer.setLayout(useDefaultLabelQHBoxLayout)

        self.genderlabel = QLabel()
        self.genderlabel.setText('性别:')
        listLayout.addWidget(self.genderlabel, row_loc, 0)
        self.gendergroup = QButtonGroup()
        self.gendergroup.exclusive()
        self.genderButton0 = QCheckBox(u'女')
        self.genderButton0.setChecked(False)
        self.genderButton0.stateChanged.connect(self.btnstate_isfemale)
        self.genderButton1 = QCheckBox(u'男')
        self.genderButton1.setChecked(False)
        self.genderButton1.stateChanged.connect(self.btnstate_ismale)
        self.gendergroup.addButton(self.genderButton0)
        self.gendergroup.addButton(self.genderButton1)
        listLayout.addWidget(self.genderButton0, row_loc, 1)
        listLayout.addWidget(self.genderButton1, row_loc, 2)
        row_loc += 1

        self.agelabel = QLabel()
        self.agelabel.setText('年龄:')
        # listLayout.addWidget(self.agelabel, row_loc, 0)
        self.agegroup = QButtonGroup()
        self.agegroup.exclusive()
        self.ageButton0 = QCheckBox(u'青少年')
        self.ageButton0.setChecked(False)
        self.ageButton0.stateChanged.connect(self.btnstate_young)
        self.ageButton1 = QCheckBox(u'中年')
        self.ageButton1.setChecked(False)
        self.ageButton1.stateChanged.connect(self.btnstate_middle)
        self.ageButton2 = QCheckBox(u'老年')
        self.ageButton2.setChecked(False)
        self.ageButton2.stateChanged.connect(self.btnstate_old)
        self.ageButton3 = QCheckBox(u'儿童')
        self.ageButton3.setChecked(False)
        self.ageButton3.stateChanged.connect(self.btnstate_children)
        self.agegroup.addButton(self.ageButton0)
        self.agegroup.addButton(self.ageButton1)
        self.agegroup.addButton(self.ageButton2)
        self.agegroup.addButton(self.ageButton3)
        # listLayout.addWidget(self.ageButton0, row_loc, 1)
        # listLayout.addWidget(self.ageButton1, row_loc, 2)
        # listLayout.addWidget(self.ageButton2, row_loc, 3)
        # listLayout.addWidget(self.ageButton3, row_loc, 4)
        # row_loc += 1

        self.masklabel = QLabel()
        self.masklabel.setText('口罩:')
        listLayout.addWidget(self.masklabel, row_loc, 0)
        self.maskgroup = QButtonGroup()
        self.maskgroup.exclusive()
        self.maskButton0 = QCheckBox(u'否')
        self.maskButton0.setChecked(False)
        self.maskButton0.stateChanged.connect(self.btnstate_nomask)
        self.maskButton1 = QCheckBox(u'是')
        self.maskButton1.setChecked(False)
        self.maskButton1.stateChanged.connect(self.btnstate_mask)
        self.maskgroup.addButton(self.maskButton0)
        self.maskgroup.addButton(self.maskButton1)
        listLayout.addWidget(self.maskButton0, row_loc, 1)
        listLayout.addWidget(self.maskButton1, row_loc, 2)
        row_loc += 1

        self.mouthlabel = QLabel()
        self.mouthlabel.setText('张嘴:')
        listLayout.addWidget(self.mouthlabel, row_loc, 0)
        self.mouthgroup = QButtonGroup()
        self.mouthgroup.exclusive()
        self.mouthButton0 = QCheckBox(u'否')
        self.mouthButton0.setChecked(False)
        self.mouthButton0.stateChanged.connect(self.btnstate_closemouth)
        self.mouthButton1 = QCheckBox(u'是')
        self.mouthButton1.setChecked(False)
        self.mouthButton1.stateChanged.connect(self.btnstate_openmouth)
        self.mouthButton2 = QCheckBox(u'不确定(戴口罩)')
        self.mouthButton2.setChecked(False)
        self.mouthButton2.stateChanged.connect(self.btnstate_uncertainmouth)
        self.mouthgroup.addButton(self.mouthButton0)
        self.mouthgroup.addButton(self.mouthButton1)
        self.mouthgroup.addButton(self.mouthButton2)
        listLayout.addWidget(self.mouthButton0, row_loc, 1)
        listLayout.addWidget(self.mouthButton1, row_loc, 2)
        listLayout.addWidget(self.mouthButton2, row_loc, 3)
        row_loc += 1

        self.eyeglasslabel = QLabel()
        self.eyeglasslabel.setText('眼镜:')
        listLayout.addWidget(self.eyeglasslabel, row_loc, 0)
        self.eyeglassgroup = QButtonGroup()
        self.eyeglassgroup.exclusive()
        self.eyeglassButton0 = QCheckBox(u'否')
        self.eyeglassButton0.setChecked(False)
        self.eyeglassButton0.stateChanged.connect(self.btnstate_noeyeglass)
        self.eyeglassButton1 = QCheckBox(u'是')
        self.eyeglassButton1.setChecked(False)
        self.eyeglassButton1.stateChanged.connect(self.btnstate_eyeglass)
        self.eyeglassgroup.addButton(self.eyeglassButton0)
        self.eyeglassgroup.addButton(self.eyeglassButton1)
        listLayout.addWidget(self.eyeglassButton0, row_loc, 1)
        listLayout.addWidget(self.eyeglassButton1, row_loc, 2)
        row_loc += 1

        self.sunglasslabel = QLabel()
        self.sunglasslabel.setText('墨镜:')
        listLayout.addWidget(self.sunglasslabel, row_loc, 0)
        self.sunglassgroup = QButtonGroup()
        self.sunglassgroup.exclusive()
        self.sunglassButton0 = QCheckBox(u'否')
        self.sunglassButton0.setChecked(False)
        self.sunglassButton0.stateChanged.connect(self.btnstate_nosunglass)
        self.sunglassButton1 = QCheckBox(u'是')
        self.sunglassButton1.setChecked(False)
        self.sunglassButton1.stateChanged.connect(self.btnstate_sunglass)
        self.sunglassgroup.addButton(self.sunglassButton0)
        self.sunglassgroup.addButton(self.sunglassButton1)
        listLayout.addWidget(self.sunglassButton0, row_loc, 1)
        listLayout.addWidget(self.sunglassButton1, row_loc, 2)
        row_loc += 1


        self.eyelabel = QLabel()
        self.eyelabel.setText('闭眼:')
        listLayout.addWidget(self.eyelabel, row_loc, 0)
        self.eyegroup = QButtonGroup()
        self.eyegroup.exclusive()
        self.eyeButton0 = QCheckBox(u'否')
        self.eyeButton0.setChecked(False)
        self.eyeButton0.stateChanged.connect(self.btnstate_openeye)
        self.eyeButton1 = QCheckBox(u'是')
        self.eyeButton1.setChecked(False)
        self.eyeButton1.stateChanged.connect(self.btnstate_closeeye)
        self.eyeButton2 = QCheckBox(u'不确定(戴墨镜)')
        self.eyeButton2.setChecked(False)
        self.eyeButton2.stateChanged.connect(self.btnstate_uncertaineye)
        self.eyegroup.addButton(self.eyeButton0)
        self.eyegroup.addButton(self.eyeButton1)
        self.eyegroup.addButton(self.eyeButton2)
        listLayout.addWidget(self.eyeButton0, row_loc, 1)
        listLayout.addWidget(self.eyeButton1, row_loc, 2)
        listLayout.addWidget(self.eyeButton2, row_loc, 3)
        row_loc += 1

        self.emotionlabel = QLabel()
        self.emotionlabel.setText('表情:')
        # listLayout.addWidget(self.emotionlabel, row_loc, 0)
        self.emotiongroup = QButtonGroup()
        self.emotiongroup.exclusive()
        self.emotionButton0 = QCheckBox(u'正常')
        self.emotionButton0.setChecked(False)
        self.emotionButton0.stateChanged.connect(self.btnstate_norm_emotion)
        self.emotionButton1 = QCheckBox(u'笑')
        self.emotionButton1.setChecked(False)
        self.emotionButton1.stateChanged.connect(self.btnstate_laugh)
        self.emotionButton2 = QCheckBox(u'惊讶')
        self.emotionButton2.setChecked(False)
        self.emotionButton2.stateChanged.connect(self.btnstate_shock)
        self.emotiongroup.addButton(self.emotionButton0)
        self.emotiongroup.addButton(self.emotionButton1)
        self.emotiongroup.addButton(self.emotionButton2)
        # listLayout.addWidget(self.emotionButton0, row_loc, 1)
        # listLayout.addWidget(self.emotionButton1, row_loc, 2)
        # listLayout.addWidget(self.emotionButton2, row_loc, 3)
        row_loc += 1

        self.blurrinesslabel = QLabel()
        self.blurrinesslabel.setText('模糊:')
        listLayout.addWidget(self.blurrinesslabel, row_loc, 0)
        self.blurrinessgroup = QButtonGroup()
        self.blurrinessgroup.exclusive()
        self.blurrinessButton0 = QCheckBox(u'否')
        self.blurrinessButton0.setChecked(False)
        self.blurrinessButton0.stateChanged.connect(self.btnstate_noblur)
        self.blurrinessButton1 = QCheckBox(u'是')
        self.blurrinessButton1.setChecked(False)
        self.blurrinessButton1.stateChanged.connect(self.btnstate_blur)
        self.blurrinessgroup.addButton(self.blurrinessButton0)
        self.blurrinessgroup.addButton(self.blurrinessButton1)
        listLayout.addWidget(self.blurrinessButton0, row_loc, 1)
        listLayout.addWidget(self.blurrinessButton1, row_loc, 2)
        row_loc += 1

        self.illuminationlabel = QLabel()
        self.illuminationlabel.setText('光照:')
        listLayout.addWidget(self.illuminationlabel, row_loc, 0)
        self.illuminationgroup = QButtonGroup()
        self.illuminationgroup.exclusive()
        self.illuminationButton0 = QCheckBox(u'正常')
        self.illuminationButton0.setChecked(False)
        self.illuminationButton0.stateChanged.connect(self.btnstate_norm_illumination)
        self.illuminationButton1 = QCheckBox(u'昏暗')
        self.illuminationButton1.setChecked(False)
        self.illuminationButton1.stateChanged.connect(self.btnstate_dim)
        self.illuminationButton2 = QCheckBox(u'明亮')
        self.illuminationButton2.setChecked(False)
        self.illuminationButton2.stateChanged.connect(self.btnstate_bright)
        self.illuminationButton3 = QCheckBox(u'逆光')
        self.illuminationButton3.setChecked(False)
        self.illuminationButton3.stateChanged.connect(self.btnstate_backlight)
        self.illuminationButton4 = QCheckBox(u'阴阳脸')
        self.illuminationButton4.setChecked(False)
        self.illuminationButton4.stateChanged.connect(self.btnstate_yinyang)
        self.illuminationgroup.addButton(self.illuminationButton0)
        self.illuminationgroup.addButton(self.illuminationButton1)
        self.illuminationgroup.addButton(self.illuminationButton2)
        self.illuminationgroup.addButton(self.illuminationButton3)
        self.illuminationgroup.addButton(self.illuminationButton4)
        listLayout.addWidget(self.illuminationButton0, row_loc, 1)
        listLayout.addWidget(self.illuminationButton1, row_loc, 2)
        listLayout.addWidget(self.illuminationButton2, row_loc, 3)
        listLayout.addWidget(self.illuminationButton3, row_loc, 4)
        listLayout.addWidget(self.illuminationButton4, row_loc, 5)
        row_loc += 1


        self.yawlabel = QLabel()
        self.yawlabel.setText('yaw(左右翻转角度):')
        # listLayout.addWidget(self.yawlabel, row_loc, 0)
        self.yawgroup = QButtonGroup()
        self.yawgroup.exclusive()
        self.yawButton0 = QCheckBox(u'Normal')
        self.yawButton0.setChecked(False)
        self.yawButton0.stateChanged.connect(self.btnstate_norm_yaw)
        self.yawButton1 = QCheckBox(u'30。(2 eyes)')
        self.yawButton1.setChecked(False)
        self.yawButton1.stateChanged.connect(self.btnstate_yaw_30)
        self.yawButton2 = QCheckBox(u'60。(1 eye)')
        self.yawButton2.setChecked(False)
        self.yawButton2.stateChanged.connect(self.btnstate_yaw_60)
        self.yawgroup.addButton(self.yawButton0)
        self.yawgroup.addButton(self.yawButton1)
        self.yawgroup.addButton(self.yawButton2)
        # listLayout.addWidget(self.yawButton0, row_loc, 1)
        # listLayout.addWidget(self.yawButton1, row_loc, 2)
        # listLayout.addWidget(self.yawButton2, row_loc, 3)
        # row_loc += 1

        self.pitchlabel = QLabel()
        self.pitchlabel.setText('pitch(上下翻转角度):')
        # listLayout.addWidget(self.pitchlabel, row_loc, 0)
        self.pitchgroup = QButtonGroup()
        self.pitchgroup.exclusive()
        self.pitchButton0 = QCheckBox(u'Normal')
        self.pitchButton0.setChecked(False)
        self.pitchButton0.stateChanged.connect(self.btnstate_norm_pitch)
        self.pitchButton1 = QCheckBox(u'20。up')
        self.pitchButton1.setChecked(False)
        self.pitchButton1.stateChanged.connect(self.btnstate_pitch_20up)
        self.pitchButton2 = QCheckBox(u'45。up')
        self.pitchButton2.setChecked(False)
        self.pitchButton2.stateChanged.connect(self.btnstate_pitch_45up)
        self.pitchButton3 = QCheckBox(u'20。down')
        self.pitchButton3.setChecked(False)
        self.pitchButton3.stateChanged.connect(self.btnstate_pitch_20down)
        self.pitchButton4 = QCheckBox(u'45。down')
        self.pitchButton4.setChecked(False)
        self.pitchButton4.stateChanged.connect(self.btnstate_pitch_45down)
        self.pitchgroup.addButton(self.pitchButton0)
        self.pitchgroup.addButton(self.pitchButton1)
        self.pitchgroup.addButton(self.pitchButton2)
        self.pitchgroup.addButton(self.pitchButton3)
        self.pitchgroup.addButton(self.pitchButton4)
        # listLayout.addWidget(self.pitchButton0, row_loc, 1)
        # listLayout.addWidget(self.pitchButton1, row_loc, 2)
        # listLayout.addWidget(self.pitchButton2, row_loc, 3)
        # listLayout.addWidget(self.pitchButton3, row_loc, 4)
        # listLayout.addWidget(self.pitchButton4, row_loc, 5)
        # row_loc += 1

        self.rolllabel = QLabel()
        self.rolllabel.setText('roll(平面旋转角度):')
        # listLayout.addWidget(self.rolllabel, row_loc, 0)
        self.rollgroup = QButtonGroup()
        self.rollgroup.exclusive()
        self.rollButton0 = QCheckBox(u'Normal')
        self.rollButton0.setChecked(False)
        self.rollButton0.stateChanged.connect(self.btnstate_norm_roll)
        self.rollButton1 = QCheckBox(u'20。 roll')
        self.rollButton1.setChecked(False)
        self.rollButton1.stateChanged.connect(self.btnstate_roll_20)
        self.rollButton2 = QCheckBox(u'45。 roll')
        self.rollButton2.setChecked(False)
        self.rollButton2.stateChanged.connect(self.btnstate_roll_45)
        self.rollgroup.addButton(self.rollButton0)
        self.rollgroup.addButton(self.rollButton1)
        self.rollgroup.addButton(self.rollButton2)
        # listLayout.addWidget(self.rollButton0, row_loc, 1)
        # listLayout.addWidget(self.rollButton1, row_loc, 2)
        # listLayout.addWidget(self.rollButton2, row_loc, 3)
        # row_loc += 1

        self.editButton = QToolButton()
        self.editButton.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self.ageButton = QToolButton()
        self.ageButton.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)

        # Add some of widgets to listLayout
        #listLayout.addWidget(self.editButton)
        # listLayout.addWidget(self.ageButton,row_loc,0)
        # listLayout.addWidget(useDefaultLabelContainer,row_loc,1)

        # Create and add a widget for showing current label items
        self.labelList = QListWidget()
        labelListContainer = QWidget()
        labelListContainer.setLayout(listLayout)
        self.labelList.itemActivated.connect(self.labelSelectionChanged)
        self.labelList.itemSelectionChanged.connect(self.labelSelectionChanged)
        self.labelList.itemDoubleClicked.connect(self.editAge)
        # Connect to itemChanged to detect checkbox changes.
        self.labelList.itemChanged.connect(self.labelItemChanged)
        # listLayout.addWidget(self.labelList)

        self.dock = QDockWidget(u'人脸属性', self)
        self.dock.setObjectName(u'Labels')
        self.dock.setWidget(labelListContainer)

        # Tzutalin 20160906 : Add file list and dock to move faster
        self.fileListWidget = QListWidget()
        self.fileListWidget.itemDoubleClicked.connect(self.fileitemDoubleClicked)
        filelistLayout = QVBoxLayout()
        filelistLayout.setContentsMargins(0, 0, 0, 0)
        filelistLayout.addWidget(self.fileListWidget)
        fileListContainer = QWidget()
        fileListContainer.setLayout(filelistLayout)
        self.filedock = QDockWidget(u'File List', self)
        self.filedock.setObjectName(u'Files')
        self.filedock.setWidget(fileListContainer)

        self.zoomWidget = ZoomWidget()
        self.colorDialog = ColorDialog(parent=self)

        self.canvas = Canvas()
        self.canvas.zoomRequest.connect(self.zoomRequest)

        scroll = QScrollArea()
        scroll.setWidget(self.canvas)
        scroll.setWidgetResizable(True)
        self.scrollBars = {
            Qt.Vertical: scroll.verticalScrollBar(),
            Qt.Horizontal: scroll.horizontalScrollBar()
        }
        self.scrollArea = scroll
        self.canvas.scrollRequest.connect(self.scrollRequest)

        self.canvas.newShape.connect(self.newShape)
        self.canvas.shapeMoved.connect(self.setDirty)
        self.canvas.selectionChanged.connect(self.shapeSelectionChanged)
        self.canvas.drawingPolygon.connect(self.toggleDrawingSensitive)

        self.setCentralWidget(scroll)
        self.addDockWidget(Qt.RightDockWidgetArea, self.dock)
        # Tzutalin 20160906 : Add file list and dock to move faster
        self.addDockWidget(Qt.RightDockWidgetArea, self.filedock)
        self.dockFeatures = QDockWidget.DockWidgetClosable\
            | QDockWidget.DockWidgetFloatable
        self.dock.setFeatures(self.dock.features() ^ self.dockFeatures)

        # Actions
        action = partial(newAction, self)
        quit = action('&Quit', self.close,
                      'Ctrl+Q', 'quit', u'Quit application')

        open = action('&Open', self.openFile,
                      'Ctrl+O', 'open', u'Open image or label file')

        opendir = action('&Open Dir', self.openDir,
                         'Ctrl+u', 'open', u'Open Dir')

        changeSavedir = action('&Change Save Dir', self.changeSavedir,
                               'Ctrl+r', 'open', u'Change default saved Annotation dir')

        openAnnotation = action('&Open Annotation', self.openAnnotation,
                                'Ctrl+Shift+O', 'open', u'Open Annotation')

        openNextImg = action('&Next Image', self.openNextImg,
                             'right', 'next', u'Open Next')

        openPrevImg = action('&Prev Image', self.openPrevImg,
                             'left', 'prev', u'Open Prev')

        verify = action('&Verify Image', self.verifyImg,
                        'space', 'verify', u'Verify Image')

        save = action('&Save', self.saveFile,
                      'down', 'save', u'Save labels to file', enabled=False)
        saveAs = action('&Save As', self.saveFileAs,
                        'Ctrl+Shift+S', 'save-as', u'Save labels to a different file',
                        enabled=False)
        close = action('&Close', self.closeFile,
                       'Ctrl+W', 'close', u'Close current file')
        color1 = action('Box &Line Color', self.chooseColor1,
                        'Ctrl+L', 'color_line', u'Choose Box line color')
        color2 = action('Box &Fill Color', self.chooseColor2,
                        'Ctrl+Shift+L', 'color', u'Choose Box fill color')

        createMode = action('Create\nRectBox', self.setCreateMode,
                            'Ctrl+N', 'new', u'Start drawing Boxs', enabled=False)
        editMode = action('&Edit\nRectBox', self.setEditMode,
                          'Ctrl+J', 'edit', u'Move and edit Boxs', enabled=False)

        create = action('Create\nRectBox', self.createShape,
                        'up', 'new', u'Draw a new Box', enabled=False)
        delete = action('Delete\nRectBox', self.deleteSelectedShape,
                        'Delete', 'delete', u'Delete', enabled=False)
        copy = action('&Duplicate\nRectBox', self.copySelectedShape,
                      'Ctrl+D', 'copy', u'Create a duplicate of the selected Box',
                      enabled=False)

        advancedMode = action('&Advanced Mode', self.toggleAdvancedMode,
                              'Ctrl+Shift+A', 'expert', u'Switch to advanced mode',
                              checkable=True)

        hideAll = action('&Hide\nRectBox', partial(self.togglePolygons, False),
                         'Ctrl+H', 'hide', u'Hide all Boxs',
                         enabled=False)
        showAll = action('&Show\nRectBox', partial(self.togglePolygons, True),
                         'Ctrl+A', 'hide', u'Show all Boxs',
                         enabled=False)

        help = action('&Tutorial', self.tutorial, 'Ctrl+T', 'help',
                      u'Show demos')

        zoom = QWidgetAction(self)
        zoom.setDefaultWidget(self.zoomWidget)
        self.zoomWidget.setWhatsThis(
            u"Zoom in or out of the image. Also accessible with"
            " %s and %s from the canvas." % (fmtShortcut("Ctrl+[-+]"),
                                             fmtShortcut("Ctrl+Wheel")))
        self.zoomWidget.setEnabled(False)

        zoomIn = action('Zoom &In', partial(self.addZoom, 10),
                        'Ctrl++', 'zoom-in', u'Increase zoom level', enabled=False)
        zoomOut = action('&Zoom Out', partial(self.addZoom, -10),
                         'Ctrl+-', 'zoom-out', u'Decrease zoom level', enabled=False)
        zoomOrg = action('&Original size', partial(self.setZoom, 100),
                         'Ctrl+=', 'zoom', u'Zoom to original size', enabled=False)
        fitWindow = action('&Fit Window', self.setFitWindow,
                           'Ctrl+F', 'fit-window', u'Zoom follows window size',
                           checkable=True, enabled=False)
        fitWidth = action('Fit &Width', self.setFitWidth,
                          'Ctrl+Shift+F', 'fit-width', u'Zoom follows window width',
                          checkable=True, enabled=False)
        # Group zoom controls into a list for easier toggling.
        zoomActions = (self.zoomWidget, zoomIn, zoomOut,
                       zoomOrg, fitWindow, fitWidth)
        self.zoomMode = self.MANUAL_ZOOM
        self.scalers = {
            self.FIT_WINDOW: self.scaleFitWindow,
            self.FIT_WIDTH: self.scaleFitWidth,
            # Set to one to scale to 100% when loading files.
            self.MANUAL_ZOOM: lambda: 1,
        }

        edit = action('Edit Label', self.editLabel,
                      'Ctrl+1', 'edit', u'Modify the information of the selected Box',
                      enabled=False)
        self.editButton.setDefaultAction(edit)

        age = action('Edit Age', self.editAge,
                      'Ctrl+E', 'age', u'Modify the age of the selected Box',
                      enabled=False)
        self.ageButton.setDefaultAction(age)

        shapeLineColor = action('Shape &Line Color', self.chshapeLineColor,
                                icon='color_line', tip=u'Change the line color for this specific shape',
                                enabled=False)
        shapeFillColor = action('Shape &Fill Color', self.chshapeFillColor,
                                icon='color', tip=u'Change the fill color for this specific shape',
                                enabled=False)

        labels = self.dock.toggleViewAction()
        labels.setText('Show/Hide Label Panel')
        labels.setShortcut('Ctrl+Shift+L')

        # Lavel list context menu.
        labelMenu = QMenu()
        addActions(labelMenu, (edit, age, delete))
        self.labelList.setContextMenuPolicy(Qt.CustomContextMenu)
        self.labelList.customContextMenuRequested.connect(
            self.popLabelListMenu)

        # Store actions for further handling.
        self.actions = struct(save=save, saveAs=saveAs, open=open, close=close,
                              lineColor=color1, fillColor=color2,
                              create=create, delete=delete, edit=edit, copy=copy,
                              createMode=createMode, editMode=editMode, advancedMode=advancedMode,
                              shapeLineColor=shapeLineColor, shapeFillColor=shapeFillColor,
                              zoom=zoom, zoomIn=zoomIn, zoomOut=zoomOut, zoomOrg=zoomOrg,
                              fitWindow=fitWindow, fitWidth=fitWidth,
                              zoomActions=zoomActions,
                              fileMenuActions=(
                                  open, opendir, save, saveAs, close, quit),
                              beginner=(), advanced=(),
                              editMenu=(edit, copy, delete,
                                        None, color1, color2),
                              beginnerContext=(create, edit, copy, delete),
                              advancedContext=(createMode, editMode, edit, copy,
                                               delete, shapeLineColor, shapeFillColor),
                              onLoadActive=(
                                  close, create, createMode, editMode),
                              onShapesPresent=(saveAs, hideAll, showAll),
                              age = age)

        self.menus = struct(
            file=self.menu('&File'),
            edit=self.menu('&Edit'),
            view=self.menu('&View'),
            help=self.menu('&Help'),
            recentFiles=QMenu('Open &Recent'),
            labelList=labelMenu)

        # Auto saving : Enble auto saving if pressing next
        self.autoSaving = QAction("Auto Saving", self)
        self.autoSaving.setCheckable(True)

        # Sync single class mode from PR#106
        self.singleClassMode = QAction("Single Class Mode", self)
        self.singleClassMode.setShortcut("Ctrl+Shift+S")
        self.singleClassMode.setCheckable(True)
        self.lastLabel = None

        addActions(self.menus.file,
                   (open, opendir, changeSavedir, openAnnotation, self.menus.recentFiles, save, saveAs, close, None, quit))
        addActions(self.menus.help, (help,))
        addActions(self.menus.view, (
            self.autoSaving,
            self.singleClassMode,
            labels, advancedMode, None,
            hideAll, showAll, None,
            zoomIn, zoomOut, zoomOrg, None,
            fitWindow, fitWidth))

        self.menus.file.aboutToShow.connect(self.updateFileMenu)

        # Custom context menu for the canvas widget:
        addActions(self.canvas.menus[0], self.actions.beginnerContext)
        addActions(self.canvas.menus[1], (
            action('&Copy here', self.copyShape),
            action('&Move here', self.moveShape)))

        self.tools = self.toolbar('Tools')
        self.actions.beginner = (
            open, opendir, changeSavedir, openNextImg, openPrevImg, verify, save, None, create, copy, delete, None,
            zoomIn, zoom, zoomOut, fitWindow, fitWidth)

        self.actions.advanced = (
            open, opendir, changeSavedir, openNextImg, openPrevImg, save, None,
            createMode, editMode, None,
            hideAll, showAll)

        self.statusBar().showMessage('%s started.' % __appname__)
        self.statusBar().show()

        # Application state.
        self.image = QImage()
        self.filePath = ustr(defaultFilename)
        self.recentFiles = []
        self.maxRecent = 7
        self.lineColor = None
        self.fillColor = None
        self.zoom_level = 100
        self.fit_window = False
        # Add Chris
        self.isfemale = False
        self.ismale = False

        self.young = False
        self.middle = False
        self.old = False
        self.children = False

        self.nomask = False
        self.mask = False

        self.closemouth = False
        self.openmouth = False
        self.uncertainmouth = False

        self.noeyeglass = False
        self.eyeglass = False

        self.nosunglass = False
        self.sunglass = False

        self.openeye = False
        self.closeeye = False
        self.uncertaineye = False

        self.norm_emotion = False
        self.laugh = False
        self.shock = False

        self.blur = False
        self.noblur = False

        self.norm_illumination = False
        self.dim = False
        self.bright = False
        self.backlight = False
        self.yinyang = False

        self.norm_yaw = False
        self.yaw_30 = False
        self.yaw_60 = False

        self.norm_roll = False
        self.roll_20 = False
        self.roll_45 = False

        self.norm_pitch = False
        self.pitch_20up = False
        self.pitch_45up = False
        self.pitch_20down = False
        self.pitch_45down = False

        # Load predefined classes to the list
        self.loadPredefinedClasses(defaultPrefdefClassFile)

        self.settings = Settings()
        self.settings.load()
        settings = self.settings

        ## Fix the compatible issue for qt4 and qt5. Convert the QStringList to python list
        if settings.get(SETTING_RECENT_FILES):
            if have_qstring():
                recentFileQStringList = settings.get(SETTING_RECENT_FILES)
                self.recentFiles = [ustr(i) for i in recentFileQStringList]
            else:
                self.recentFiles = recentFileQStringList = settings.get(SETTING_RECENT_FILES)

        size = settings.get(SETTING_WIN_SIZE, QSize(600, 500))
        position = settings.get(SETTING_WIN_POSE, QPoint(0, 0))
        self.resize(size)
        self.move(position)
        saveDir = ustr(settings.get(SETTING_SAVE_DIR, None))
        self.lastOpenDir = ustr(settings.get(SETTING_LAST_OPEN_DIR, None))
        if saveDir is not None and os.path.exists(saveDir):
            self.defaultSaveDir = saveDir
            self.statusBar().showMessage('%s started. Annotation will be saved to %s' %
                                         (__appname__, self.defaultSaveDir))
            self.statusBar().show()

        # or simply:
        # self.restoreGeometry(settings[SETTING_WIN_GEOMETRY]
        self.restoreState(settings.get(SETTING_WIN_STATE, QByteArray()))
        self.lineColor = QColor(settings.get(SETTING_LINE_COLOR, Shape.line_color))
        self.fillColor = QColor(settings.get(SETTING_FILL_COLOR, Shape.fill_color))
        Shape.line_color = self.lineColor
        Shape.fill_color = self.fillColor

        # Add chris
        Shape.isfemale = self.isfemale
        Shape.ismale = self.ismale

        Shape.young = self.young
        Shape.middle = self.middle
        Shape.old = self.old
        Shape.children = self.children

        Shape.nomask = self.nomask
        Shape.mask = self.mask

        Shape.closemouth = self.closemouth
        Shape.openmouth = self.openmouth
        Shape.uncertainmouth = self.uncertainmouth

        Shape.noeyeglass = self.noeyeglass
        Shape.eyeglass = self.eyeglass

        Shape.nosunglass = self.nosunglass
        Shape.sunglass = self.sunglass

        Shape.openeye = self.openeye
        Shape.closeeye = self.closeeye
        Shape.uncertaineye = self.uncertaineye

        Shape.norm_emotion = self.norm_emotion
        Shape.laugh = self.laugh
        Shape.shock = self.shock

        Shape.noblur = self.noblur
        Shape.blur = self.blur

        Shape.norm_illumination = self.norm_illumination
        Shape.dim = self.dim
        Shape.bright = self.bright
        Shape.backlight = self.backlight
        Shape.yinyang = self.yinyang

        Shape.norm_yaw = self.norm_yaw
        Shape.yaw_30 = self.yaw_30
        Shape.yaw_60 = self.yaw_60

        Shape.norm_roll = self.norm_roll
        Shape.roll_20 = self.roll_20
        Shape.roll_45 = self.roll_45

        Shape.norm_pitch = self.norm_pitch
        Shape.pitch_20up = self.pitch_20up
        Shape.pitch_45up = self.pitch_45up
        Shape.pitch_20down = self.pitch_20down
        Shape.pitch_45down = self.pitch_45down

        def xbool(x):
            if isinstance(x, QVariant):
                return x.toBool()
            return bool(x)

        if xbool(settings.get(SETTING_ADVANCE_MODE, False)):
            self.actions.advancedMode.setChecked(True)
            self.toggleAdvancedMode()

        # Populate the File menu dynamically.
        self.updateFileMenu()
        # Since loading the file may take some time, make sure it runs in the
        # background.
        self.queueEvent(partial(self.loadFile, self.filePath or ""))

        # Callbacks:
        self.zoomWidget.valueChanged.connect(self.paintCanvas)

        self.populateModeActions()

    ## Support Functions ##

    def noShapes(self):
        return not self.itemsToShapes

    def toggleAdvancedMode(self, value=True):
        self._beginner = not value
        self.canvas.setEditing(True)
        self.populateModeActions()
        self.editButton.setVisible(not value)
        if value:
            self.actions.createMode.setEnabled(True)
            self.actions.editMode.setEnabled(False)
            self.dock.setFeatures(self.dock.features() | self.dockFeatures)
        else:
            self.dock.setFeatures(self.dock.features() ^ self.dockFeatures)

    def populateModeActions(self):
        if self.beginner():
            tool, menu = self.actions.beginner, self.actions.beginnerContext
        else:
            tool, menu = self.actions.advanced, self.actions.advancedContext
        self.tools.clear()
        addActions(self.tools, tool)
        self.canvas.menus[0].clear()
        addActions(self.canvas.menus[0], menu)
        self.menus.edit.clear()
        actions = (self.actions.create,) if self.beginner()\
            else (self.actions.createMode, self.actions.editMode)
        addActions(self.menus.edit, actions + self.actions.editMenu)

    def setBeginner(self):
        self.tools.clear()
        addActions(self.tools, self.actions.beginner)

    def setAdvanced(self):
        self.tools.clear()
        addActions(self.tools, self.actions.advanced)

    def setDirty(self):
        self.dirty = True
        self.actions.save.setEnabled(True)

    def setClean(self):
        self.dirty = False
        self.actions.save.setEnabled(False)
        self.actions.create.setEnabled(True)

    def toggleActions(self, value=True):
        """Enable/Disable widgets which depend on an opened image."""
        for z in self.actions.zoomActions:
            z.setEnabled(value)
        for action in self.actions.onLoadActive:
            action.setEnabled(value)

    def queueEvent(self, function):
        QTimer.singleShot(0, function)

    def resetButton(self):
        self.genderButton0.setChecked(True)
        self.genderButton1.setChecked(False)
        self.ageButton0.setChecked(True)
        self.ageButton1.setChecked(False)
        self.ageButton2.setChecked(False)
        self.ageButton3.setChecked(False)
        self.maskButton0.setChecked(True)
        self.maskButton1.setChecked(False)
        self.mouthButton0.setChecked(True)
        self.mouthButton1.setChecked(False)
        self.mouthButton2.setChecked(False)
        self.eyeglassButton0.setChecked(True)
        self.eyeglassButton1.setChecked(False)
        self.sunglassButton0.setChecked(True)
        self.sunglassButton1.setChecked(False)
        self.eyeButton0.setChecked(True)
        self.eyeButton1.setChecked(False)
        self.eyeButton2.setChecked(False)
        self.emotionButton0.setChecked(True)
        self.emotionButton1.setChecked(False)
        self.emotionButton2.setChecked(False)
        self.blurrinessButton0.setChecked(True)
        self.blurrinessButton1.setChecked(False)
        self.illuminationButton0.setChecked(True)
        self.illuminationButton1.setChecked(False)
        self.illuminationButton2.setChecked(False)
        self.illuminationButton3.setChecked(False)
        self.illuminationButton4.setChecked(False)
        self.yawButton0.setChecked(True)
        self.yawButton1.setChecked(False)
        self.yawButton2.setChecked(False)
        self.rollButton0.setChecked(True)
        self.rollButton1.setChecked(False)
        self.rollButton2.setChecked(False)
        self.pitchButton0.setChecked(True)
        self.pitchButton1.setChecked(False)
        self.pitchButton2.setChecked(False)
        self.pitchButton3.setChecked(False)
        self.pitchButton4.setChecked(False)

    def status(self, message, delay=5000):
        self.statusBar().showMessage(message, delay)

    def resetState(self):
        self.itemsToShapes.clear()
        self.shapesToItems.clear()
        self.labelList.clear()
        self.filePath = None
        self.imageData = None
        self.labelFile = None
        self.canvas.resetState()

    def currentItem(self):
        items = self.labelList.selectedItems()
        if items:
            return items[0]
        return None

    def addRecentFile(self, filePath):
        if filePath in self.recentFiles:
            self.recentFiles.remove(filePath)
        elif len(self.recentFiles) >= self.maxRecent:
            self.recentFiles.pop()
        self.recentFiles.insert(0, filePath)

    def beginner(self):
        return self._beginner

    def advanced(self):
        return not self.beginner()

    ## Callbacks ##
    def tutorial(self):
        subprocess.Popen([self.screencastViewer, self.screencast])

    def createShape(self):
        assert self.beginner()
        self.canvas.setEditing(False)
        self.actions.create.setEnabled(False)

    def toggleDrawingSensitive(self, drawing=True):
        """In the middle of drawing, toggling between modes should be disabled."""
        self.actions.editMode.setEnabled(not drawing)
        if not drawing and self.beginner():
            # Cancel creation.
            print('Cancel creation.')
            self.canvas.setEditing(True)
            self.canvas.restoreCursor()
            self.actions.create.setEnabled(True)

    def toggleDrawMode(self, edit=True):
        self.canvas.setEditing(edit)
        self.actions.createMode.setEnabled(edit)
        self.actions.editMode.setEnabled(not edit)

    def setCreateMode(self):
        assert self.advanced()
        self.toggleDrawMode(False)

    def setEditMode(self):
        assert self.advanced()
        self.toggleDrawMode(True)
        self.labelSelectionChanged()

    def updateFileMenu(self):
        currFilePath = self.filePath

        def exists(filename):
            return os.path.exists(filename)
        menu = self.menus.recentFiles
        menu.clear()
        files = [f for f in self.recentFiles if f !=
                 currFilePath and exists(f)]
        for i, f in enumerate(files):
            icon = newIcon('labels')
            action = QAction(
                icon, '&%d %s' % (i + 1, QFileInfo(f).fileName()), self)
            action.triggered.connect(partial(self.loadRecent, f))
            menu.addAction(action)

    def popLabelListMenu(self, point):
        self.menus.labelList.exec_(self.labelList.mapToGlobal(point))

    def editLabel(self, item=None):
        if not self.canvas.editing():
            return
        item = item if item else self.currentItem()
        text = self.labelDialog.popUp(item.text())
        if text is not None:
            item.setText(text)
            self.setDirty()

    def editAge(self, item=None):
        if not self.canvas.editing():
            return
        item = item if item else self.currentItem()
        text = self.ageDialog.popUp(item.text())
        if text is not None:
            item.setText(text)
            self.setDirty()

    # Tzutalin 20160906 : Add file list and dock to move faster
    def fileitemDoubleClicked(self, item=None):
        currIndex = self.mImgList.index(ustr(item.text()))
        if currIndex < len(self.mImgList):
            filename = self.mImgList[currIndex]
            if filename:
                self.loadFile(filename)

    # React to canvas signals.
    def shapeSelectionChanged(self, selected=False):
        if self._noSelectionSlot:
            self._noSelectionSlot = False
        else:
            shape = self.canvas.selectedShape
            if shape:
                self.shapesToItems[shape].setSelected(True)
            else:
                self.labelList.clearSelection()
        self.actions.delete.setEnabled(selected)
        self.actions.copy.setEnabled(selected)
        self.actions.edit.setEnabled(selected)
        self.actions.age.setEnabled(selected)
        self.actions.shapeLineColor.setEnabled(selected)
        self.actions.shapeFillColor.setEnabled(selected)

    def addLabel(self, shape):
        item = HashableQListWidgetItem(shape.label)
        item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
        item.setCheckState(Qt.Checked)
        self.itemsToShapes[item] = shape
        self.shapesToItems[shape] = item
        # item.setText(str(shape.age))
        self.labelList.addItem(item)
        for action in self.actions.onShapesPresent:
            action.setEnabled(True)

    def remLabel(self, shape):
        if shape is None:
            # print('rm empty label')
            return
        item = self.shapesToItems[shape]
        self.labelList.takeItem(self.labelList.row(item))
        del self.shapesToItems[shape]
        del self.itemsToShapes[item]

    def loadLabels(self, shapes):
        s = []
        for label, points, line_color, fill_color, \
            isfemale, ismale, \
            young, middle, old, children,\
            nomask, mask,\
            closemouth, openmouth, uncertainmouth,\
            noeyeglass, eyeglass,\
            nosunglass, sunglass,\
            openeye, closeeye, uncertaineye, \
            norm_emotion, laugh, shock, \
            noblur, blur, \
            norm_illumination,dim, bright, backlight, yinyang,\
            norm_yaw, yaw_30, yaw_60,\
            norm_roll, roll_20, roll_45,\
            norm_pitch, pitch_20up, pitch_45up, pitch_20down, pitch_45down in shapes:
            shape = Shape(label=label,
                          isfemale=isfemale, ismale=ismale,
                          young=young, middle=middle, old=old, children=children,
                          nomask=nomask, mask=mask,
                          closemouth=closemouth, openmouth=openmouth, uncertainmouth=uncertainmouth,
                          noeyeglass=noeyeglass, eyeglass=eyeglass,
                          nosunglass=nosunglass, sunglass=sunglass,
                          openeye=openeye, closeeye=closeeye, uncertaineye=uncertaineye,
                          norm_emotion=norm_emotion, laugh=laugh, shock=shock,
                          noblur=noblur, blur=blur,
                          norm_illumination=norm_illumination, dim=dim, bright=bright, backlight=backlight, yinyang=yinyang,
                          norm_yaw=norm_yaw, yaw_30=yaw_30, yaw_60=yaw_60,
                          norm_roll=norm_roll, roll_20=roll_20, roll_45=roll_45,
                          norm_pitch=norm_pitch, pitch_20up=pitch_20up, pitch_45up=pitch_45up, pitch_20down=pitch_20down, pitch_45down=pitch_45down)
            for x, y in points:
                shape.addPoint(QPointF(x, y))
            shape.close()
            s.append(shape)
            self.addLabel(shape)

            if line_color:
                shape.line_color = QColor(*line_color)
            if fill_color:
                shape.fill_color = QColor(*fill_color)

        self.canvas.loadShapes(s)

    def saveLabels(self, annotationFilePath):
        annotationFilePath = ustr(annotationFilePath)
        if self.labelFile is None:
            self.labelFile = LabelFile()
            self.labelFile.verified = self.canvas.verified

        def format_shape(s):
            return dict(label=s.label,
                        line_color=s.line_color.getRgb()
                        if s.line_color != self.lineColor else None,
                        fill_color=s.fill_color.getRgb()
                        if s.fill_color != self.fillColor else None,
                        points=[(p.x(), p.y()) for p in s.points],
                       # add chris
                        isfemale = s.isfemale, ismale = s.ismale,
                        young = s.young, middle = s.middle, old = s.old, children = s.children,
                        nomask = s.nomask, mask = s.mask,
                        closemouth = s.closemouth, openmouth = s.openmouth, uncertainmouth = s.uncertainmouth,
                        noeyeglass = s.noeyeglass, eyeglass = s.eyeglass,
                        nosunglass = s.nosunglass, sunglass = s.sunglass,
                        openeye = s.openeye, closeeye = s.closeeye, uncertaineye = s.uncertaineye,
                        norm_emotion=s.norm_emotion, laugh=s.laugh, shock=s.shock,
                        noblur=s.noblur, blur=s.blur,
                        norm_illumination=s.norm_illumination, dim=s.dim, bright=s.bright, backlight=s.backlight, yinyang=s.yinyang,
                        norm_yaw=s.norm_yaw, yaw_30=s.yaw_30, yaw_60=s.yaw_60,
                        norm_roll=s.norm_roll, roll_20=s.roll_20, roll_45=s.roll_45,
                        norm_pitch=s.norm_pitch, pitch_20up=s.pitch_20up, pitch_45up=s.pitch_45up, pitch_20down=s.pitch_20down, pitch_45down=s.pitch_45down)

        shapes = [format_shape(shape) for shape in self.canvas.shapes]
        # Can add differrent annotation formats here
        try:
            if self.usingPascalVocFormat is True:
                print ('Img: ' + self.filePath + ' -> Its xml: ' + annotationFilePath)
                self.labelFile.savePascalVocFormat(annotationFilePath, shapes, self.filePath, self.imageData,
                                                   self.lineColor.getRgb(), self.fillColor.getRgb())
            else:
                print ('self.labelFile.save')
                self.labelFile.save(annotationFilePath, shapes, self.filePath, self.imageData,
                                    self.lineColor.getRgb(), self.fillColor.getRgb())
            return True
        except LabelFileError as e:
            self.errorMessage(u'Error saving label data',
                              u'<b>%s</b>' % e)
            return False

    def copySelectedShape(self):
        self.addLabel(self.canvas.copySelectedShape())
        # fix copy and delete
        self.shapeSelectionChanged(True)

    def printthisshape(self,shape):
        # print("age:",)
        # print(shape.age)

        print("Gender: ", end='')
        if shape.isfemale:
            print("female")
        elif shape.ismale:
            print("male")
        else:
            print("None!")

        print("Age: ", end='')
        if shape.young:
            print("young")
        elif shape.middle:
            print("middle")
        elif shape.old:
            print("old")
        elif shape.children:
            print("children")
        else:
            print("None!")

        print("Mask: ", end='')
        if shape.nomask:
            print("nomask")
        elif shape.mask:
            print("mask")
        else:
            print("None!")

        print("Mouth: ", end='')
        if shape.closemouth:
            print("closemouth")
        elif shape.openmouth:
            print("openmouth")
        elif shape.uncertainmouth:
            print("uncertainmouth")
        else:
            print("None!")

        print("Eyeglass: ", end='')
        if shape.noeyeglass:
            print("noeyeglass")
        elif shape.eyeglass:
            print("eyeglass")
        else:
            print("None!")

        print("Sunglass: ", end='')
        if shape.nosunglass:
            print("nosunglass")
        elif shape.sunglass:
            print("sunglass")
        else:
            print("None!")

        print("Eye: ", end='')
        if shape.closeeye:
            print("closeeye")
        elif shape.openeye:
            print("openeye")
        elif shape.uncertaineye:
            print("uncertaineye")
        else:
            print("None!")

        print("Emotion: ", end='')
        if shape.norm_emotion:
            print("norm emotion")
        elif shape.laugh:
            print("laugh")
        elif shape.shock:
            print("shock")
        else:
            print("None!")

        print("Blurriness: ", end='')
        if shape.noblur:
            print("no blur")
        elif shape.blur:
            print("blur")
        else:
            print("None!")

        print("Illumination: ", end='')
        if shape.norm_illumination:
            print("norm illumination")
        elif shape.dim:
            print("dim")
        elif shape.backlight:
            print("backlight")
        elif shape.yinyang:
            print("yinyang")
        else:
            print("None!")

        print("yaw: ", end='')
        if shape.norm_yaw:
            print("norm yaw")
        elif shape.yaw_30:
            print("yaw_30")
        elif shape.yaw_60:
            print("yaw_60")
        else:
            print("None!")

        print("roll: ", end='')
        if shape.norm_roll:
            print("norm roll")
        elif shape.roll_20:
            print("roll_20")
        elif shape.roll_45:
            print("roll_45")
        else:
            print("None!")

        print("pitch: ", end='')
        if shape.norm_pitch:
            print("norm pitch")
        elif shape.pitch_20up:
            print("pitch_20up")
        elif shape.pitch_45up:
            print("pitch_45up")
        elif shape.pitch_20down:
            print("pitch_20down")
        elif shape.pitch_45down:
            print("pitch_45down")
        else:
            print("None!")

    def labelSelectionChanged(self):
        item = self.currentItem()
        if item and self.canvas.editing():
            self._noSelectionSlot = True
            self.canvas.selectShape(self.itemsToShapes[item])
            shape = self.itemsToShapes[item]
            # Add Chrisif

            print("\n labelSelectionChanged:")
            self.printthisshape(shape)

            if shape.isfemale:
                self.genderButton0.setChecked(True)
            if shape.ismale:
                self.genderButton1.setChecked(True)

            if shape.young:
                self.ageButton0.setChecked(True)
            if shape.middle:
                self.ageButton1.setChecked(True)
            if shape.old:
                self.ageButton2.setChecked(True)
            if shape.children:
                self.ageButton3.setChecked(True)

            if shape.nomask:
                self.maskButton0.setChecked(True)
            if shape.mask:
                self.maskButton1.setChecked(True)

            if shape.closemouth:
                self.mouthButton0.setChecked(True)
            if shape.openmouth:
                self.mouthButton1.setChecked(True)
            if shape.uncertainmouth:
                self.mouthButton2.setChecked(True)

            if shape.noeyeglass:
                self.eyeglassButton0.setChecked(True)
            if shape.eyeglass:
                self.eyeglassButton1.setChecked(True)

            if shape.nosunglass:
                self.sunglassButton0.setChecked(True)
            if shape.sunglass:
                self.sunglassButton1.setChecked(True)

            if shape.openeye:
                self.eyeButton0.setChecked(True)
            if shape.closeeye:
                self.eyeButton1.setChecked(True)
            if shape.uncertaineye:
                self.eyeButton2.setChecked(True)

            if shape.norm_emotion:
                self.emotionButton0.setChecked(True)
            if shape.laugh:
                self.emotionButton1.setChecked(True)
            if shape.shock:
                self.emotionButton2.setChecked(True)

            if shape.noblur:
                self.blurrinessButton0.setChecked(True)
            if shape.blur:
                self.blurrinessButton1.setChecked(True)

            if shape.norm_illumination:
                self.illuminationButton0.setChecked(True)
            if shape.dim:
                self.illuminationButton1.setChecked(True)
            if shape.bright:
                self.illuminationButton2.setChecked(True)
            if shape.backlight:
                self.illuminationButton3.setChecked(True)
            if shape.yinyang:
                self.illuminationButton4.setChecked(True)


            if shape.norm_yaw:
                self.yawButton0.setChecked(True)
            if shape.yaw_30:
                self.yawButton1.setChecked(True)
            if shape.yaw_60:
                self.yawButton2.setChecked(True)

            if shape.norm_roll:
                self.rollButton0.setChecked(True)
            if shape.roll_20:
                self.rollButton1.setChecked(True)
            if shape.roll_45:
                self.rollButton2.setChecked(True)

            if shape.norm_pitch:
                self.pitchButton0.setChecked(True)
            if shape.pitch_20up:
                self.pitchButton1.setChecked(True)
            if shape.pitch_45up:
                self.pitchButton2.setChecked(True)
            if shape.pitch_20down:
                self.pitchButton3.setChecked(True)
            if shape.pitch_45down:
                self.pitchButton4.setChecked(True)


    '''
    def labelItemChanged(self, item):
        print "labelItemChanged"
        shape = self.itemsToShapes[item]
        label = item.text()
        if label != shape.label:
            shape.label = item.text()
            self.setDirty()
        else:  # User probably changed item visibility
            self.canvas.setShapeVisible(shape, item.checkState() == Qt.Checked)
    '''

    def labelItemChanged(self, item):
        print("ageItemChanged")
        shape = self.itemsToShapes[item]
        age = item.text()
        if age != shape.age:
            shape.age = item.text()
            self.setDirty()
        else:  # User probably changed item visibility
            self.canvas.setShapeVisible(shape, item.checkState() == Qt.Checked)

    # Callback functions:
    def newShape(self):
        """Pop-up and give focus to the label editor.

        position MUST be in global coordinates.
        """
        '''
        if not self.useDefaultLabelCheckbox.isChecked() or not self.defaultLabelTextLine.text():
            if len(self.labelHist) > 0:
                self.labelDialog = LabelDialog(
                    parent=self, listItem=self.labelHist)

            # Sync single class mode from PR#106
            if self.singleClassMode.isChecked() and self.lastLabel:
                text = self.lastLabel
            else:
                text = self.labelDialog.popUp(text=self.prevLabelText)
                self.lastLabel = text
        else:
            text = self.defaultLabelTextLine.text()
        '''
        text = 'face'

        self.prevLabelText = text
        self.addLabel(self.canvas.setLastLabel(text))
        if self.beginner():  # Switch to edit mode.
            self.canvas.setEditing(True)
            self.actions.create.setEnabled(True)
        else:
            self.actions.editMode.setEnabled(True)
        self.setDirty()

    def scrollRequest(self, delta, orientation):
        units = - delta / (8 * 15)
        bar = self.scrollBars[orientation]
        bar.setValue(bar.value() + bar.singleStep() * units)

    def setZoom(self, value):
        self.actions.fitWidth.setChecked(False)
        self.actions.fitWindow.setChecked(False)
        self.zoomMode = self.MANUAL_ZOOM
        self.zoomWidget.setValue(value)

    def addZoom(self, increment=10):
        self.setZoom(self.zoomWidget.value() + increment)

    def zoomRequest(self, delta):
        # get the current scrollbar positions
        # calculate the percentages ~ coordinates
        h_bar = self.scrollBars[Qt.Horizontal]
        v_bar = self.scrollBars[Qt.Vertical]

        # get the current maximum, to know the difference after zooming
        h_bar_max = h_bar.maximum()
        v_bar_max = v_bar.maximum()

        # get the cursor position and canvas size
        # calculate the desired movement from 0 to 1
        # where 0 = move left
        #       1 = move right
        # up and down analogous
        cursor = QCursor()
        pos = cursor.pos()
        relative_pos = QWidget.mapFromGlobal(self, pos)

        cursor_x = relative_pos.x()
        cursor_y = relative_pos.y()

        w = self.scrollArea.width()
        h = self.scrollArea.height()

        # the scaling from 0 to 1 has some padding
        # you don't have to hit the very leftmost pixel for a maximum-left movement
        margin = 0.1
        move_x = (cursor_x - margin * w) / (w - 2 * margin * w)
        move_y = (cursor_y - margin * h) / (h - 2 * margin * h)

        # clamp the values from 0 to 1
        move_x = min(max(move_x, 0), 1)
        move_y = min(max(move_y, 0), 1)

        # zoom in
        units = delta / (8 * 15)
        scale = 10
        self.addZoom(scale * units)

        # get the difference in scrollbar values
        # this is how far we can move
        d_h_bar_max = h_bar.maximum() - h_bar_max
        d_v_bar_max = v_bar.maximum() - v_bar_max

        # get the new scrollbar values
        new_h_bar_value = h_bar.value() + move_x * d_h_bar_max
        new_v_bar_value = v_bar.value() + move_y * d_v_bar_max

        h_bar.setValue(new_h_bar_value)
        v_bar.setValue(new_v_bar_value)

    def setFitWindow(self, value=True):
        if value:
            self.actions.fitWidth.setChecked(False)
        self.zoomMode = self.FIT_WINDOW if value else self.MANUAL_ZOOM
        self.adjustScale()

    def setFitWidth(self, value=True):
        if value:
            self.actions.fitWindow.setChecked(False)
        self.zoomMode = self.FIT_WIDTH if value else self.MANUAL_ZOOM
        self.adjustScale()

    def togglePolygons(self, value):
        for item, shape in self.itemsToShapes.items():
            item.setCheckState(Qt.Checked if value else Qt.Unchecked)

    def loadFile(self, filePath=None):
        """Load the specified file, or the last opened file if None."""
        self.resetButton()
        self.resetState()

        self.canvas.setEnabled(False)
        if filePath is None:
            filePath = self.settings.get(SETTING_FILENAME)

        unicodeFilePath = ustr(filePath)
        # Tzutalin 20160906 : Add file list and dock to move faster
        # Highlight the file item
        if unicodeFilePath and self.fileListWidget.count() > 0:
            index = self.mImgList.index(unicodeFilePath)
            fileWidgetItem = self.fileListWidget.item(index)
            fileWidgetItem.setSelected(True)

        if unicodeFilePath and os.path.exists(unicodeFilePath):
            if LabelFile.isLabelFile(unicodeFilePath):
                try:
                    self.labelFile = LabelFile(unicodeFilePath)
                except LabelFileError as e:
                    self.errorMessage(u'Error opening file',
                                      (u"<p><b>%s</b></p>"
                                       u"<p>Make sure <i>%s</i> is a valid label file.")
                                      % (e, unicodeFilePath))
                    self.status("Error reading %s" % unicodeFilePath)
                    return False
                self.imageData = self.labelFile.imageData
                self.lineColor = QColor(*self.labelFile.lineColor)
                self.fillColor = QColor(*self.labelFile.fillColor)
            else:
                # Load image:
                # read data first and store for saving into label file.
                self.imageData = read(unicodeFilePath, None)
                self.labelFile = None
            image = QImage.fromData(self.imageData)
            if image.isNull():
                self.errorMessage(u'Error opening file',
                                  u"<p>Make sure <i>%s</i> is a valid image file." % unicodeFilePath)
                self.status("Error reading %s" % unicodeFilePath)
                return False
            self.status("Loaded %s" % os.path.basename(unicodeFilePath))
            self.image = image
            self.filePath = unicodeFilePath
            self.canvas.loadPixmap(QPixmap.fromImage(image))
            if self.labelFile:
                self.loadLabels(self.labelFile.shapes)
            self.setClean()
            self.canvas.setEnabled(True)
            self.adjustScale(initial=True)
            self.paintCanvas()
            self.addRecentFile(self.filePath)
            self.toggleActions(True)

            # Label xml file and show bound box according to its filename
            if self.usingPascalVocFormat is True:
                if self.defaultSaveDir is not None:
                    basename = os.path.basename(
                        os.path.splitext(self.filePath)[0]) + XML_EXT
                    xmlPath = os.path.join(self.defaultSaveDir, basename)
                    self.loadPascalXMLByFilename(xmlPath)
                else:
                    xmlPath = os.path.splitext(filePath)[0] + XML_EXT
                    if os.path.isfile(xmlPath):
                        self.loadPascalXMLByFilename(xmlPath)

            self.setWindowTitle(__appname__ + ' ' + filePath)

            # Default : select last item if there is at least one item
            if self.labelList.count():
                self.labelList.setCurrentItem(self.labelList.item(self.labelList.count()-1))
                self.labelList.item(self.labelList.count()-1).setSelected(True)

            self.canvas.setFocus(True)
            return True
        return False

    def resizeEvent(self, event):
        if self.canvas and not self.image.isNull()\
           and self.zoomMode != self.MANUAL_ZOOM:
            self.adjustScale()
        super(MainWindow, self).resizeEvent(event)

    def paintCanvas(self):
        assert not self.image.isNull(), "cannot paint null image"
        self.canvas.scale = 0.01 * self.zoomWidget.value()
        self.canvas.adjustSize()
        self.canvas.update()

    def adjustScale(self, initial=False):
        value = self.scalers[self.FIT_WINDOW if initial else self.zoomMode]()
        self.zoomWidget.setValue(int(100 * value))

    def scaleFitWindow(self):
        """Figure out the size of the pixmap in order to fit the main widget."""
        e = 2.0  # So that no scrollbars are generated.
        w1 = self.centralWidget().width() - e
        h1 = self.centralWidget().height() - e
        a1 = w1 / h1
        # Calculate a new scale value based on the pixmap's aspect ratio.
        w2 = self.canvas.pixmap.width() - 0.0
        h2 = self.canvas.pixmap.height() - 0.0
        a2 = w2 / h2
        return w1 / w2 if a2 >= a1 else h1 / h2

    def scaleFitWidth(self):
        # The epsilon does not seem to work too well here.
        w = self.centralWidget().width() - 2.0
        return w / self.canvas.pixmap.width()

    def closeEvent(self, event):
        if not self.mayContinue():
            event.ignore()
        settings = self.settings
        # If it loads images from dir, don't load it at the begining
        if self.dirname is None:
            settings[SETTING_FILENAME] = self.filePath if self.filePath else ''
        else:
            settings[SETTING_FILENAME] = ''

        settings[SETTING_WIN_SIZE] = self.size()
        settings[SETTING_WIN_POSE] = self.pos()
        settings[SETTING_WIN_STATE] = self.saveState()
        settings[SETTING_LINE_COLOR] = self.lineColor
        settings[SETTING_FILL_COLOR] = self.fillColor
        settings[SETTING_RECENT_FILES] = self.recentFiles
        settings[SETTING_ADVANCE_MODE] = not self._beginner
        if self.defaultSaveDir is not None and len(self.defaultSaveDir) > 1:
            settings[SETTING_SAVE_DIR] = ustr(self.defaultSaveDir)
        else:
            settings[SETTING_SAVE_DIR] = ""

        if self.lastOpenDir is not None and len(self.lastOpenDir) > 1:
            settings[SETTING_LAST_OPEN_DIR] = self.lastOpenDir
        else:
            settings[SETTING_LAST_OPEN_DIR] = ""

        settings.save()
    ## User Dialogs ##

    def loadRecent(self, filename):
        if self.mayContinue():
            self.loadFile(filename)

    def scanAllImages(self, folderPath):
        extensions = ['.jpeg', '.jpg', '.png', '.bmp']
        images = []

        for root, dirs, files in os.walk(folderPath):
            for file in files:
                if file.lower().endswith(tuple(extensions)):
                    relativePath = os.path.join(root, file)
                    path = ustr(os.path.abspath(relativePath))
                    images.append(path)
        images.sort(key=lambda x: x.lower())
        return images

    def changeSavedir(self, _value=False):
        if self.defaultSaveDir is not None:
            path = ustr(self.defaultSaveDir)
        else:
            path = '.'

        dirpath = ustr(QFileDialog.getExistingDirectory(self,
                                                       '%s - Save to the directory' % __appname__, path,  QFileDialog.ShowDirsOnly
                                                       | QFileDialog.DontResolveSymlinks))

        if dirpath is not None and len(dirpath) > 1:
            self.defaultSaveDir = dirpath

        self.statusBar().showMessage('%s . Annotation will be saved to %s' %
                                     ('Change saved folder', self.defaultSaveDir))
        self.statusBar().show()

    def openAnnotation(self, _value=False):
        if self.filePath is None:
            self.statusBar().showMessage('Please select image first')
            self.statusBar().show()
            return

        path = os.path.dirname(ustr(self.filePath))\
            if self.filePath else '.'
        if self.usingPascalVocFormat:
            filters = "Open Annotation XML file (%s)" % ' '.join(['*.xml'])
            filename = ustr(QFileDialog.getOpenFileName(self,'%s - Choose a xml file' % __appname__, path, filters))
            if filename:
                if isinstance(filename, (tuple, list)):
                    filename = filename[0]
            self.loadPascalXMLByFilename(filename)

    def openDir(self, _value=False):
        if not self.mayContinue():
            return

        path = os.path.dirname(self.filePath)\
            if self.filePath else '.'

        if self.lastOpenDir is not None and len(self.lastOpenDir) > 1:
            path = self.lastOpenDir

        dirpath = ustr(QFileDialog.getExistingDirectory(self,
                                                     '%s - Open Directory' % __appname__, path,  QFileDialog.ShowDirsOnly
                                                     | QFileDialog.DontResolveSymlinks))

        if dirpath is not None and len(dirpath) > 1:
            self.lastOpenDir = dirpath

        self.dirname = dirpath
        self.filePath = None
        self.fileListWidget.clear()
        self.mImgList = self.scanAllImages(dirpath)
        self.openNextImg()
        for imgPath in self.mImgList:
            item = QListWidgetItem(imgPath)
            self.fileListWidget.addItem(item)

    def verifyImg(self, _value=False):
        # Proceding next image without dialog if having any label
         if self.filePath is not None:
            try:
                self.labelFile.toggleVerify()
            except AttributeError:
                # If the labelling file does not exist yet, create if and
                # re-save it with the verified attribute.
                self.saveFile()
                self.labelFile.toggleVerify()

            self.canvas.verified = self.labelFile.verified
            self.paintCanvas()
            self.saveFile()

    def openPrevImg(self, _value=False):
        # Proceding prev image without dialog if having any label
        if self.autoSaving.isChecked() and self.defaultSaveDir is not None:
            if self.dirty is True:
                self.saveFile()

        if not self.mayContinue():
            return

        if len(self.mImgList) <= 0:
            return

        if self.filePath is None:
            return

        currIndex = self.mImgList.index(self.filePath)
        if currIndex - 1 >= 0:
            filename = self.mImgList[currIndex - 1]
            if filename:
                self.loadFile(filename)

    def openNextImg(self, _value=False):
        # Proceding next image without dialog if having any label
        if self.autoSaving.isChecked() and self.defaultSaveDir is not None:
            if self.dirty is True:
                self.saveFile()

        if not self.mayContinue():
            return

        if len(self.mImgList) <= 0:
            return

        filename = None
        if self.filePath is None:
            filename = self.mImgList[0]
        else:
            currIndex = self.mImgList.index(self.filePath)
            if currIndex + 1 < len(self.mImgList):
                filename = self.mImgList[currIndex + 1]

        if filename:
            self.loadFile(filename)

    def openFile(self, _value=False):
        if not self.mayContinue():
            return
        path = os.path.dirname(ustr(self.filePath)) if self.filePath else '.'
        formats = ['*.%s' % fmt.data().decode("ascii").lower() for fmt in QImageReader.supportedImageFormats()]
        filters = "Image & Label files (%s)" % ' '.join(formats + ['*%s' % LabelFile.suffix])
        filename = QFileDialog.getOpenFileName(self, '%s - Choose Image or Label file' % __appname__, path, filters)
        if filename:
            if isinstance(filename, (tuple, list)):
                filename = filename[0]
            self.loadFile(filename)

    def saveFile(self, _value=False):
        if self.defaultSaveDir is not None and len(ustr(self.defaultSaveDir)):
            if self.filePath:
                imgFileName = os.path.basename(self.filePath)
                savedFileName = os.path.splitext(imgFileName)[0] + XML_EXT
                savedPath = os.path.join(ustr(self.defaultSaveDir), savedFileName)
                self._saveFile(savedPath)
        else:
            imgFileDir = os.path.dirname(self.filePath)
            imgFileName = os.path.basename(self.filePath)
            savedFileName = os.path.splitext(imgFileName)[0] + XML_EXT
            savedPath = os.path.join(imgFileDir, savedFileName)
            self._saveFile(savedPath if self.labelFile
                           else self.saveFileDialog())

    def saveFileAs(self, _value=False):
        assert not self.image.isNull(), "cannot save empty image"
        self._saveFile(self.saveFileDialog())

    def saveFileDialog(self):
        caption = '%s - Choose File' % __appname__
        filters = 'File (*%s)' % LabelFile.suffix
        openDialogPath = self.currentPath()
        dlg = QFileDialog(self, caption, openDialogPath, filters)
        dlg.setDefaultSuffix(LabelFile.suffix[1:])
        dlg.setAcceptMode(QFileDialog.AcceptSave)
        filenameWithoutExtension = os.path.splitext(self.filePath)[0]
        dlg.selectFile(filenameWithoutExtension)
        dlg.setOption(QFileDialog.DontUseNativeDialog, False)
        if dlg.exec_():
            return dlg.selectedFiles()[0]
        return ''

    def _saveFile(self, annotationFilePath):
        if annotationFilePath and self.saveLabels(annotationFilePath):
            self.setClean()
            self.statusBar().showMessage('Saved to  %s' % annotationFilePath)
            self.statusBar().show()

    def closeFile(self, _value=False):
        if not self.mayContinue():
            return
        self.resetState()
        self.setClean()
        self.toggleActions(False)
        self.canvas.setEnabled(False)
        self.actions.saveAs.setEnabled(False)

    def mayContinue(self):
        return not (self.dirty and not self.discardChangesDialog())

    def discardChangesDialog(self):
        yes, no = QMessageBox.Yes, QMessageBox.No
        msg = u'You have unsaved changes, proceed anyway?'
        return yes == QMessageBox.warning(self, u'Attention', msg, yes | no)

    def errorMessage(self, title, message):
        return QMessageBox.critical(self, title,
                                    '<p><b>%s</b></p>%s' % (title, message))

    def currentPath(self):
        return os.path.dirname(self.filePath) if self.filePath else '.'

    def chooseColor1(self):
        color = self.colorDialog.getColor(self.lineColor, u'Choose line color',
                                          default=DEFAULT_LINE_COLOR)
        if color:
            self.lineColor = color
            # Change the color for all shape lines:
            Shape.line_color = self.lineColor
            self.canvas.update()
            self.setDirty()

    def chooseColor2(self):
        color = self.colorDialog.getColor(self.fillColor, u'Choose fill color',
                                          default=DEFAULT_FILL_COLOR)
        if color:
            self.fillColor = color
            Shape.fill_color = self.fillColor
            self.canvas.update()
            self.setDirty()

    def deleteSelectedShape(self):
        self.remLabel(self.canvas.deleteSelected())
        self.setDirty()
        if self.noShapes():
            for action in self.actions.onShapesPresent:
                action.setEnabled(False)

    def chshapeLineColor(self):
        color = self.colorDialog.getColor(self.lineColor, u'Choose line color',
                                          default=DEFAULT_LINE_COLOR)
        if color:
            self.canvas.selectedShape.line_color = color
            self.canvas.update()
            self.setDirty()

    def chshapeFillColor(self):
        color = self.colorDialog.getColor(self.fillColor, u'Choose fill color',
                                          default=DEFAULT_FILL_COLOR)
        if color:
            self.canvas.selectedShape.fill_color = color
            self.canvas.update()
            self.setDirty()

    def copyShape(self):
        self.canvas.endMove(copy=True)
        self.addLabel(self.canvas.selectedShape)
        self.setDirty()

    def moveShape(self):
        self.canvas.endMove(copy=False)
        self.setDirty()

    def loadPredefinedClasses(self, predefClassesFile):
        if os.path.exists(predefClassesFile) is True:
            with codecs.open(predefClassesFile, 'r', 'utf8') as f:
                for line in f:
                    line = line.strip()
                    if self.labelHist is None:
                        self.lablHist = [line]
                    else:
                        self.labelHist.append(line)

    def loadPascalXMLByFilename(self, xmlPath):
        if self.filePath is None:
            return
        if os.path.isfile(xmlPath) is False:
            return

        tVocParseReader = PascalVocReader(xmlPath)
        shapes = tVocParseReader.getShapes()
        self.loadLabels(shapes)
        self.canvas.verified = tVocParseReader.verified


    #button state:
    # Add chris
    def btnstate_isfemale(self, item=None):
        if not self.canvas.editing():
            return
        item = self.currentItem()
        if not item:  # If not selected Item, take the first one
            item = self.labelList.item(self.labelList.count() - 1)
        isfemale = self.genderButton0.isChecked()
        try:
            shape = self.itemsToShapes[item]
            if isfemale != shape.isfemale:
                shape.isfemale = isfemale
                self.setDirty()
            else:  # User probably changed item visibility
                self.canvas.setShapeVisible(shape, item.checkState() == Qt.Checked)
        except:
            pass

    def btnstate_ismale(self, item=None):
        if not self.canvas.editing():
            return
        item = self.currentItem()
        if not item:  # If not selected Item, take the first one
            item = self.labelList.item(self.labelList.count() - 1)
        ismale = self.genderButton1.isChecked()
        try:
            shape = self.itemsToShapes[item]
            if ismale != shape.ismale:
                shape.ismale = ismale
                self.setDirty()
            else:  # User probably changed item visibility
                self.canvas.setShapeVisible(shape, item.checkState() == Qt.Checked)
        except:
            pass

    def btnstate_young(self, item=None):
        if not self.canvas.editing():
            return
        item = self.currentItem()
        if not item:  # If not selected Item, take the first one
            item = self.labelList.item(self.labelList.count() - 1)
        young = self.ageButton0.isChecked()
        try:
            shape = self.itemsToShapes[item]
            if young != shape.young:
                shape.young = young
                self.setDirty()
            else:  # User probably changed item visibility
                self.canvas.setShapeVisible(shape, item.checkState() == Qt.Checked)
        except:
            pass

    def btnstate_middle(self, item=None):
        if not self.canvas.editing():
            return
        item = self.currentItem()
        if not item:  # If not selected Item, take the first one
            item = self.labelList.item(self.labelList.count() - 1)
        middle = self.ageButton1.isChecked()
        try:
            shape = self.itemsToShapes[item]
            if middle != shape.middle:
                shape.middle = middle
                self.setDirty()
            else:  # User probably changed item visibility
                self.canvas.setShapeVisible(shape, item.checkState() == Qt.Checked)
        except:
            pass

    def btnstate_old(self, item=None):
        if not self.canvas.editing():
            return
        item = self.currentItem()
        if not item:  # If not selected Item, take the first one
            item = self.labelList.item(self.labelList.count() - 1)
        old = self.ageButton2.isChecked()
        try:
            shape = self.itemsToShapes[item]
            if old != shape.old:
                shape.old = old
                self.setDirty()
            else:  # User probably changed item visibility
                self.canvas.setShapeVisible(shape, item.checkState() == Qt.Checked)
        except:
            pass

    def btnstate_children(self, item=None):
        if not self.canvas.editing():
            return
        item = self.currentItem()
        if not item:  # If not selected Item, take the first one
            item = self.labelList.item(self.labelList.count() - 1)
        children = self.ageButton3.isChecked()
        try:
            shape = self.itemsToShapes[item]
            if children != shape.children:
                shape.children = children
                self.setDirty()
            else:  # User probably changed item visibility
                self.canvas.setShapeVisible(shape, item.checkState() == Qt.Checked)
        except:
            pass

    def btnstate_nomask(self, item=None):
        if not self.canvas.editing():
            return
        item = self.currentItem()
        if not item:  # If not selected Item, take the first one
            item = self.labelList.item(self.labelList.count() - 1)
        nomask = self.maskButton0.isChecked()
        try:
            shape = self.itemsToShapes[item]
            if nomask != shape.nomask:
                shape.nomask = nomask
                self.setDirty()
            else:  # User probably changed item visibility
                self.canvas.setShapeVisible(shape, item.checkState() == Qt.Checked)
        except:
            pass

    def btnstate_mask(self, item=None):
        if not self.canvas.editing():
            return
        item = self.currentItem()
        if not item:  # If not selected Item, take the first one
            item = self.labelList.item(self.labelList.count() - 1)
        mask = self.maskButton1.isChecked()
        try:
            shape = self.itemsToShapes[item]
            if mask != shape.mask:
                shape.mask = mask
                self.setDirty()
            else:  # User probably changed item visibility
                self.canvas.setShapeVisible(shape, item.checkState() == Qt.Checked)
            if shape.mask:
                shape.uncertainmouth = True
                self.mouthButton2.setChecked(True)
        except:
            pass

    def btnstate_noeyeglass(self, item=None):
        if not self.canvas.editing():
            return
        item = self.currentItem()
        if not item:  # If not selected Item, take the first one
            item = self.labelList.item(self.labelList.count() - 1)
        noeyeglass = self.eyeglassButton0.isChecked()
        try:
            shape = self.itemsToShapes[item]
            if noeyeglass != shape.noeyeglass:
                shape.noeyeglass = noeyeglass
                self.setDirty()
            else:  # User probably changed item visibility
                self.canvas.setShapeVisible(shape, item.checkState() == Qt.Checked)
        except:
            pass

    def btnstate_eyeglass(self, item=None):
        if not self.canvas.editing():
            return
        item = self.currentItem()
        if not item:  # If not selected Item, take the first one
            item = self.labelList.item(self.labelList.count() - 1)
        eyeglass = self.eyeglassButton1.isChecked()
        try:
            shape = self.itemsToShapes[item]
            if eyeglass != shape.eyeglass:
                shape.eyeglass = eyeglass
                self.setDirty()
            else:  # User probably changed item visibility
                self.canvas.setShapeVisible(shape, item.checkState() == Qt.Checked)
        except:
            pass

    def btnstate_nosunglass(self, item=None):
        if not self.canvas.editing():
            return
        item = self.currentItem()
        if not item:  # If not selected Item, take the first one
            item = self.labelList.item(self.labelList.count() - 1)
        nosunglass = self.sunglassButton0.isChecked()
        try:
            shape = self.itemsToShapes[item]
            if nosunglass != shape.nosunglass:
                shape.nosunglass = nosunglass
                self.setDirty()
            else:  # User probably changed item visibility
                self.canvas.setShapeVisible(shape, item.checkState() == Qt.Checked)
        except:
            pass

    def btnstate_sunglass(self, item=None):
        if not self.canvas.editing():
            return
        item = self.currentItem()
        if not item:  # If not selected Item, take the first one
            item = self.labelList.item(self.labelList.count() - 1)
        sunglass = self.sunglassButton1.isChecked()
        try:
            shape = self.itemsToShapes[item]
            if sunglass != shape.sunglass:
                shape.sunglass = sunglass
                self.setDirty()
            else:  # User probably changed item visibility
                self.canvas.setShapeVisible(shape, item.checkState() == Qt.Checked)
            if shape.sunglass:
                shape.uncertaineye = True
                self.eyeButton2.setChecked(True)
        except:
            pass

    def btnstate_closemouth(self, item=None):
        if not self.canvas.editing():
            return
        item = self.currentItem()
        if not item:  # If not selected Item, take the first one
            item = self.labelList.item(self.labelList.count() - 1)
        closemouth = self.mouthButton0.isChecked()
        try:
            shape = self.itemsToShapes[item]
            if closemouth != shape.closemouth:
                shape.closemouth = closemouth
                self.setDirty()
            else:  # User probably changed item visibility
                self.canvas.setShapeVisible(shape, item.checkState() == Qt.Checked)
        except:
            pass

    def btnstate_openmouth(self, item=None):
        if not self.canvas.editing():
            return
        item = self.currentItem()
        if not item:  # If not selected Item, take the first one
            item = self.labelList.item(self.labelList.count() - 1)
        openmouth = self.mouthButton1.isChecked()
        try:
            shape = self.itemsToShapes[item]
            if openmouth != shape.openmouth:
                shape.openmouth = openmouth
                self.setDirty()
            else:  # User probably changed item visibility
                self.canvas.setShapeVisible(shape, item.checkState() == Qt.Checked)
        except:
            pass

    def btnstate_uncertainmouth(self, item=None):
        if not self.canvas.editing():
            return
        item = self.currentItem()
        if not item:  # If not selected Item, take the first one
            item = self.labelList.item(self.labelList.count() - 1)
        uncertainmouth = self.mouthButton2.isChecked()
        try:
            shape = self.itemsToShapes[item]
            if uncertainmouth != shape.uncertainmouth:
                shape.uncertainmouth = uncertainmouth
                self.setDirty()
            else:  # User probably changed item visibility
                self.canvas.setShapeVisible(shape, item.checkState() == Qt.Checked)
            if shape.uncertainmouth:
                shape.mask = True
                self.maskButton1.setChecked(True)
        except:
            pass

    def btnstate_closeeye(self, item=None):
        if not self.canvas.editing():
            return
        item = self.currentItem()
        if not item:  # If not selected Item, take the first one
            item = self.labelList.item(self.labelList.count() - 1)
        closeeye = self.eyeButton1.isChecked()
        try:
            shape = self.itemsToShapes[item]
            if closeeye != shape.closeeye:
                shape.closeeye = closeeye
                self.setDirty()
            else:  # User probably changed item visibility
                self.canvas.setShapeVisible(shape, item.checkState() == Qt.Checked)
        except:
            pass

    def btnstate_openeye(self, item=None):
        if not self.canvas.editing():
            return
        item = self.currentItem()
        if not item:  # If not selected Item, take the first one
            item = self.labelList.item(self.labelList.count() - 1)
        openeye = self.eyeButton0.isChecked()
        try:
            shape = self.itemsToShapes[item]
            if openeye != shape.openeye:
                shape.openeye = openeye
                self.setDirty()
            else:  # User probably changed item visibility
                self.canvas.setShapeVisible(shape, item.checkState() == Qt.Checked)
        except:
            pass

    def btnstate_uncertaineye(self, item=None):
        if not self.canvas.editing():
            return
        item = self.currentItem()
        if not item:  # If not selected Item, take the first one
            item = self.labelList.item(self.labelList.count() - 1)
        uncertaineye = self.eyeButton2.isChecked()
        try:
            shape = self.itemsToShapes[item]
            if uncertaineye != shape.uncertaineye:
                shape.uncertaineye = uncertaineye
                self.setDirty()
            else:  # User probably changed item visibility
                self.canvas.setShapeVisible(shape, item.checkState() == Qt.Checked)
            if shape.uncertaineye:
                shape.sunglass = True
                self.sunglassButton1.setChecked(True)
        except:
            pass

    def btnstate_noblur(self, item=None):
        if not self.canvas.editing():
            return
        item = self.currentItem()
        if not item:  # If not selected Item, take the first one
            item = self.labelList.item(self.labelList.count() - 1)
        noblur = self.blurrinessButton0.isChecked()
        try:
            shape = self.itemsToShapes[item]
            if noblur != shape.noblur:
                shape.noblur = noblur
                self.setDirty()
            else:  # User probably changed item visibility
                self.canvas.setShapeVisible(shape, item.checkState() == Qt.Checked)
        except:
            pass

    def btnstate_blur(self, item=None):
        if not self.canvas.editing():
            return
        item = self.currentItem()
        if not item:  # If not selected Item, take the first one
            item = self.labelList.item(self.labelList.count() - 1)
        blur = self.blurrinessButton1.isChecked()
        try:
            shape = self.itemsToShapes[item]
            if blur != shape.blur:
                shape.blur = blur
                self.setDirty()
            else:  # User probably changed item visibility
                self.canvas.setShapeVisible(shape, item.checkState() == Qt.Checked)
        except:
            pass

    def btnstate_norm_emotion(self, item=None):
        if not self.canvas.editing():
            return
        item = self.currentItem()
        if not item:  # If not selected Item, take the first one
            item = self.labelList.item(self.labelList.count() - 1)
        norm_emotion = self.emotionButton0.isChecked()
        try:
            shape = self.itemsToShapes[item]
            if norm_emotion != shape.norm_emotion:
                shape.norm_emotion = norm_emotion
                self.setDirty()
            else:  # User probably changed item visibility
                self.canvas.setShapeVisible(shape, item.checkState() == Qt.Checked)
        except:
            pass

    def btnstate_laugh(self, item=None):
        if not self.canvas.editing():
            return
        item = self.currentItem()
        if not item:  # If not selected Item, take the first one
            item = self.labelList.item(self.labelList.count() - 1)
        laugh = self.emotionButton1.isChecked()
        try:
            shape = self.itemsToShapes[item]
            if laugh != shape.laugh:
                shape.laugh = laugh
                self.setDirty()
            else:  # User probably changed item visibility
                self.canvas.setShapeVisible(shape, item.checkState() == Qt.Checked)
        except:
            pass

    def btnstate_shock(self, item=None):
        if not self.canvas.editing():
            return
        item = self.currentItem()
        if not item:  # If not selected Item, take the first one
            item = self.labelList.item(self.labelList.count() - 1)
        shock = self.emotionButton2.isChecked()
        try:
            shape = self.itemsToShapes[item]
            if shock != shape.shock:
                shape.shock = shock
                self.setDirty()
            else:  # User probably changed item visibility
                self.canvas.setShapeVisible(shape, item.checkState() == Qt.Checked)
        except:
            pass

    def btnstate_norm_illumination(self, item=None):
        if not self.canvas.editing():
            return
        item = self.currentItem()
        if not item:  # If not selected Item, take the first one
            item = self.labelList.item(self.labelList.count() - 1)
        norm_illumination = self.illuminationButton0.isChecked()
        try:
            shape = self.itemsToShapes[item]
            if norm_illumination != shape.norm_illumination:
                shape.norm_illumination = norm_illumination
                self.setDirty()
            else:  # User probably changed item visibility
                self.canvas.setShapeVisible(shape, item.checkState() == Qt.Checked)
        except:
            pass

    def btnstate_dim(self, item=None):
        if not self.canvas.editing():
            return
        item = self.currentItem()
        if not item:  # If not selected Item, take the first one
            item = self.labelList.item(self.labelList.count() - 1)
        dim = self.illuminationButton1.isChecked()
        try:
            shape = self.itemsToShapes[item]
            if dim != shape.dim:
                shape.dim = dim
                self.setDirty()
            else:  # User probably changed item visibility
                self.canvas.setShapeVisible(shape, item.checkState() == Qt.Checked)
        except:
            pass

    def btnstate_bright(self, item=None):
        if not self.canvas.editing():
            return
        item = self.currentItem()
        if not item:  # If not selected Item, take the first one
            item = self.labelList.item(self.labelList.count() - 1)
        bright = self.illuminationButton2.isChecked()
        try:
            shape = self.itemsToShapes[item]
            if bright != shape.bright:
                shape.bright = bright
                self.setDirty()
            else:  # User probably changed item visibility
                self.canvas.setShapeVisible(shape, item.checkState() == Qt.Checked)
        except:
            pass

    def btnstate_backlight(self, item=None):
        if not self.canvas.editing():
            return
        item = self.currentItem()
        if not item:  # If not selected Item, take the first one
            item = self.labelList.item(self.labelList.count() - 1)
        backlight = self.illuminationButton3.isChecked()
        try:
            shape = self.itemsToShapes[item]
            if backlight != shape.backlight:
                shape.backlight = backlight
                self.setDirty()
            else:  # User probably changed item visibility
                self.canvas.setShapeVisible(shape, item.checkState() == Qt.Checked)
        except:
            pass

    def btnstate_yinyang(self, item=None):
        if not self.canvas.editing():
            return
        item = self.currentItem()
        if not item:  # If not selected Item, take the first one
            item = self.labelList.item(self.labelList.count() - 1)
        yinyang = self.illuminationButton4.isChecked()
        try:
            shape = self.itemsToShapes[item]
            if yinyang != shape.yinyang:
                shape.yinyang = yinyang
                self.setDirty()
            else:  # User probably changed item visibility
                self.canvas.setShapeVisible(shape, item.checkState() == Qt.Checked)
        except:
            pass

    def btnstate_norm_yaw(self, item=None):
        if not self.canvas.editing():
            return
        item = self.currentItem()
        if not item:  # If not selected Item, take the first one
            item = self.labelList.item(self.labelList.count() - 1)
        norm_yaw = self.yawButton0.isChecked()
        try:
            shape = self.itemsToShapes[item]
            if norm_yaw != shape.norm_yaw:
                shape.norm_yaw = norm_yaw
                self.setDirty()
            else:  # User probably changed item visibility
                self.canvas.setShapeVisible(shape, item.checkState() == Qt.Checked)
        except:
            pass

    def btnstate_yaw_30(self, item=None):
        if not self.canvas.editing():
            return
        item = self.currentItem()
        if not item:  # If not selected Item, take the first one
            item = self.labelList.item(self.labelList.count() - 1)
        yaw_30 = self.yawButton1.isChecked()
        try:
            shape = self.itemsToShapes[item]
            if yaw_30 != shape.yaw_30:
                shape.yaw_30 = yaw_30
                self.setDirty()
            else:  # User probably changed item visibility
                self.canvas.setShapeVisible(shape, item.checkState() == Qt.Checked)
        except:
            pass

    def btnstate_yaw_60(self, item=None):
        if not self.canvas.editing():
            return
        item = self.currentItem()
        if not item:  # If not selected Item, take the first one
            item = self.labelList.item(self.labelList.count() - 1)
        yaw_60 = self.yawButton2.isChecked()
        try:
            shape = self.itemsToShapes[item]
            if yaw_60 != shape.yaw_60:
                shape.yaw_60 = yaw_60
                self.setDirty()
            else:  # User probably changed item visibility
                self.canvas.setShapeVisible(shape, item.checkState() == Qt.Checked)
        except:
            pass

    def btnstate_norm_roll(self, item=None):
        if not self.canvas.editing():
            return
        item = self.currentItem()
        if not item:  # If not selected Item, take the first one
            item = self.labelList.item(self.labelList.count() - 1)
        norm_roll = self.rollButton0.isChecked()
        try:
            shape = self.itemsToShapes[item]
            if norm_roll != shape.norm_roll:
                shape.norm_roll = norm_roll
                self.setDirty()
            else:  # User probably changed item visibility
                self.canvas.setShapeVisible(shape, item.checkState() == Qt.Checked)
        except:
            pass

    def btnstate_roll_20(self, item=None):
        if not self.canvas.editing():
            return
        item = self.currentItem()
        if not item:  # If not selected Item, take the first one
            item = self.labelList.item(self.labelList.count() - 1)
        roll_20 = self.rollButton1.isChecked()
        try:
            shape = self.itemsToShapes[item]
            if roll_20 != shape.roll_20:
                shape.roll_20 = roll_20
                self.setDirty()
            else:  # User probably changed item visibility
                self.canvas.setShapeVisible(shape, item.checkState() == Qt.Checked)
        except:
            pass

    def btnstate_roll_45(self, item=None):
        if not self.canvas.editing():
            return
        item = self.currentItem()
        if not item:  # If not selected Item, take the first one
            item = self.labelList.item(self.labelList.count() - 1)
        roll_45 = self.rollButton2.isChecked()
        try:
            shape = self.itemsToShapes[item]
            if roll_45 != shape.roll_45:
                shape.roll_45 = roll_45
                self.setDirty()
            else:  # User probably changed item visibility
                self.canvas.setShapeVisible(shape, item.checkState() == Qt.Checked)
        except:
            pass

    def btnstate_norm_pitch(self, item=None):
        if not self.canvas.editing():
            return
        item = self.currentItem()
        if not item:  # If not selected Item, take the first one
            item = self.labelList.item(self.labelList.count() - 1)
        norm_pitch = self.pitchButton0.isChecked()
        try:
            shape = self.itemsToShapes[item]
            if norm_pitch != shape.norm_pitch:
                shape.norm_pitch = norm_pitch
                self.setDirty()
            else:  # User probably changed item visibility
                self.canvas.setShapeVisible(shape, item.checkState() == Qt.Checked)
        except:
            pass

    def btnstate_pitch_20up(self, item=None):
        if not self.canvas.editing():
            return
        item = self.currentItem()
        if not item:  # If not selected Item, take the first one
            item = self.labelList.item(self.labelList.count() - 1)
        pitch_20up = self.pitchButton1.isChecked()
        try:
            shape = self.itemsToShapes[item]
            if pitch_20up != shape.pitch_20up:
                shape.pitch_20up = pitch_20up
                self.setDirty()
            else:  # User probably changed item visibility
                self.canvas.setShapeVisible(shape, item.checkState() == Qt.Checked)
        except:
            pass

    def btnstate_pitch_45up(self, item=None):
        if not self.canvas.editing():
            return
        item = self.currentItem()
        if not item:  # If not selected Item, take the first one
            item = self.labelList.item(self.labelList.count() - 1)
        pitch_45up = self.pitchButton2.isChecked()
        try:
            shape = self.itemsToShapes[item]
            if pitch_45up != shape.pitch_45up:
                shape.pitch_45up = pitch_45up
                self.setDirty()
            else:  # User probably changed item visibility
                self.canvas.setShapeVisible(shape, item.checkState() == Qt.Checked)
        except:
            pass

    def btnstate_pitch_20down(self, item=None):
        if not self.canvas.editing():
            return
        item = self.currentItem()
        if not item:  # If not selected Item, take the first one
            item = self.labelList.item(self.labelList.count() - 1)
        pitch_20down = self.pitchButton3.isChecked()
        try:
            shape = self.itemsToShapes[item]
            if pitch_20down != shape.pitch_20down:
                shape.pitch_20down = pitch_20down
                self.setDirty()
            else:  # User probably changed item visibility
                self.canvas.setShapeVisible(shape, item.checkState() == Qt.Checked)
        except:
            pass

    def btnstate_pitch_45down(self, item=None):
        if not self.canvas.editing():
            return
        item = self.currentItem()
        if not item:  # If not selected Item, take the first one
            item = self.labelList.item(self.labelList.count() - 1)
        pitch_45down = self.pitchButton4.isChecked()
        try:
            shape = self.itemsToShapes[item]
            if pitch_45down != shape.pitch_45down:
                shape.pitch_45down = pitch_45down
                self.setDirty()
            else:  # User probably changed item visibility
                self.canvas.setShapeVisible(shape, item.checkState() == Qt.Checked)
        except:
            pass


def inverted(color):
    return QColor(*[255 - v for v in color.getRgb()])


def read(filename, default=None):
    try:
        with open(filename, 'rb') as f:
            return f.read()
    except:
        return default


def get_main_app(argv=[]):
    """
    Standard boilerplate Qt application code.
    Do everything but app.exec_() -- so that we can test the application in one thread
    """
    app = QApplication(argv)
    app.setApplicationName(__appname__)
    app.setWindowIcon(newIcon("app"))
    # Tzutalin 201705+: Accept extra agruments to change predefined class file
    # Usage : labelImg.py image predefClassFile
    win = MainWindow(argv[1] if len(argv) >= 2 else None,
                     argv[2] if len(argv) >= 3 else os.path.join(
                         os.path.dirname(sys.argv[0]),
                         'data', 'predefined_classes.txt'))
    win.show()
    return app, win


def main(argv=[]):
    '''construct main app and run it'''
    app, _win = get_main_app(argv)
    return app.exec_()

if __name__ == '__main__':
    sys.exit(main(sys.argv))
