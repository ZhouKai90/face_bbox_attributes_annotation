# Copyright (c) 2016 Tzutalin
# Create by TzuTaLin <tzu.ta.lin@gmail.com>

try:
    from PyQt5.QtGui import QImage
except ImportError:
    from PyQt4.QtGui import QImage

from base64 import b64encode, b64decode
from libs.pascal_voc_io import PascalVocWriter
from libs.pascal_voc_io import XML_EXT
import os.path
import sys


class LabelFileError(Exception):
    pass


class LabelFile(object):
    # It might be changed as window creates. By default, using XML ext
    # suffix = '.lif'
    suffix = XML_EXT

    def __init__(self, filename=None):
        self.shapes = ()
        self.imagePath = None
        self.imageData = None
        self.verified = False

    def savePascalVocFormat(self, filename, shapes, imagePath, imageData,
                            lineColor=None, fillColor=None, databaseSrc=None):
        imgFolderPath = os.path.dirname(imagePath)
        imgFolderName = os.path.split(imgFolderPath)[-1]
        imgFileName = os.path.basename(imagePath)
        #imgFileNameWithoutExt = os.path.splitext(imgFileName)[0]
        # Read from file path because self.imageData might be empty if saving to
        # Pascal format
        image = QImage()
        image.load(imagePath)
        imageShape = [image.height(), image.width(),
                      1 if image.isGrayscale() else 3]
        writer = PascalVocWriter(imgFolderName, imgFileName,
                                 imageShape, localImgPath=imagePath)
        writer.verified = self.verified

        for shape in shapes:
            points = shape['points']
            label = shape['label']

            # Add Chris
            if shape['ismale']:
                gender = 1
            else:
                gender = 0

            if shape['middle']:
                age = 1
            elif shape['old']:
                age = 2
            elif shape['children']:
                age = 3
            else:
                age = 0

            mask = int(shape['mask'])

            if shape['openmouth']:
                mouth = 1
            elif shape['uncertainmouth']:
                mouth = 2
            else:
                mouth = 0

            if shape['eyeglass']:
                eyeglass = 1
            else:
                eyeglass = 0

            sunglass = int(shape['sunglass'])

            if shape['closeeye']:
                eye = 1
            elif shape['uncertaineye']:
                eye = 2
            else:
                eye = 0

            if shape['laugh']:
                emotion = 1
            elif shape['shock']:
                emotion = 2
            else:
                emotion = 0

            blurriness = int(shape['blur'])

            if shape['dim']:
                illumination = 1
            elif shape['bright']:
                illumination = 2
            elif shape['backlight']:
                illumination = 3
            elif shape['yinyang']:
                illumination = 4
            else:
                illumination = 0

            if shape['yaw_30']:
                yaw = 1
            elif shape['yaw_60']:
                yaw = 2
            else:
                yaw = 0

            if shape['roll_20']:
                roll = 1
            elif shape['roll_45']:
                roll = 2
            else:
                roll = 0

            if shape['pitch_20up']:
                pitch = 1
            elif shape['pitch_45up']:
                pitch = 2
            elif shape['pitch_20down']:
                pitch = 3
            elif shape['pitch_45down']:
                pitch = 4
            else:
                pitch = 0

            bndbox = LabelFile.convertPoints2BndBox(points)
            if bndbox:
                writer.addBndBox(bndbox[0], bndbox[1], bndbox[2], bndbox[3], label, gender, age, mask,\
                             mouth, eyeglass, sunglass, eye,\
                             emotion, blurriness, illumination, yaw, roll, pitch)

        writer.save(targetFile=filename)
        return

    def toggleVerify(self):
        self.verified = not self.verified

    @staticmethod
    def isLabelFile(filename):
        fileSuffix = os.path.splitext(filename)[1].lower()
        return fileSuffix == LabelFile.suffix

    @staticmethod
    def convertPoints2BndBox(points):
        xmin = float('inf')
        ymin = float('inf')
        xmax = float('-inf')
        ymax = float('-inf')
        for p in points:
            x = p[0]
            y = p[1]
            xmin = min(x, xmin)
            ymin = min(y, ymin)
            xmax = max(x, xmax)
            ymax = max(y, ymax)

        # Martin Kersner, 2015/11/12
        # 0-valued coordinates of BB caused an error while
        # training faster-rcnn object detector.
        if xmin < 1:
            xmin = 1

        if ymin < 1:
            ymin = 1

        return (int(xmin), int(ymin), int(xmax), int(ymax))
