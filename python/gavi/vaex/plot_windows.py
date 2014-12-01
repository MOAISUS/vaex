# -*- coding: utf-8 -*-
import collections
from matplotlib.backends.backend_qt4agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.backends.backend_qt4agg import NavigationToolbar2QTAgg as NavigationToolbarQt
from matplotlib.figure import Figure
import matplotlib
from matplotlib.widgets import Lasso, LassoSelector
import matplotlib.widgets 
import matplotlib.cm
from gavi.multithreading import ThreadPool
import gavi.vaex.volumerendering
from gavi.vaex import widgets 		

from operator import itemgetter
import scipy.ndimage
import os
import gavi
import numpy as np
import functools
import time

import gavi.logging
import gavi.events
import gavi.vaex.undo as undo
import gavi.kld
import numexpr as ne
import gavi.vaex.plugin as plugin
import gavi.vaex.plugin.zoom
import gavi.vaex.plugin.vector3d
import gavi.vaex.plugin.transferfunction
import gavi.vaex.plugin.dispersions
import gavi.vaex.plugin.favorites
from gavi.vaex.grids import Grids

from numba import jit

#import subspacefind
import gavifast
subspacefind = gavifast

block = np.arange(10., dtype=np.float64)[::1]
mask = np.zeros(10, dtype=np.bool)
xmin, xmax = 3, 6
gavifast.range_check(block, mask, xmin, xmax)
print mask

logger = gavi.logging.getLogger("gavi.vaex")

from qt import *

import sys

from gavi.icons import iconfile

@jit(nopython=True)
def range_check(block, mask, xmin, xmax):
	length = len(block)
	for i in range(length):
		mask[i] = (block[i] > xmin) and (block[i] <= xmax)

import math
@jit(nopython=True)
def find_nearest_index_(datax, datay, x, y, wx, wy):
	N = len(datax)
	index = 0
	mindistance = math.sqrt((datax[0]-x)**2/wx**2 + (datay[0]-y)**2/wy**2)
	for i in range(1,N):
		distance = math.sqrt((datax[i]-x)**2/wx**2 + (datay[i]-y)**2/wy**2)
		if distance < mindistance:
			mindistance = distance
			index = i
	return index
		

def find_nearest_index(datax, datay, x, y, wx, wy):
	index = find_nearest_index_(datax, datay, x, y, wx, wy)
	distance = math.sqrt((datax[index]-x)**2/wx**2 + (datay[index]-y)**2/wy**2)
	return index, distance


@jit(nopython=True)
def find_nearest_index1d_(datax, x):
	N = len(datax)
	index = 0
	mindistance = math.sqrt((datax[0]-x)**2)
	for i in range(1,N):
		distance = math.sqrt((datax[i]-x)**2)
		if distance < mindistance:
			mindistance = distance
			index = i
	return index

def find_nearest_index1d(datax, x):
	index = find_nearest_index1d_(datax, x)
	distance = math.sqrt((datax[index]-x)**2)
	return index, distance
		
import gavi.vaex.colormaps

colormaps = []
colormap_pixmap = {}
colormaps_processed = False
refs = []
def process_colormaps():
	global colormaps_processed
	if colormaps_processed:
		return
	colormaps_processed = True
	for colormap_name in gavi.vaex.colormaps.colormaps:
		colormaps.append(colormap_name)
		Nx, Ny = 32, 16
		image, stringdata = gavi.vaex.colormaps.colormap_to_QImage(colormap_name, Nx, Ny)
		refs.append((image, stringdata))
		pixmap = QtGui.QPixmap(32*2, 32)
		pixmap.convertFromImage(image)
		colormap_pixmap[colormap_name] = pixmap
	
		
		
class Mover(object):
	def __init__(self, plot, axes):
		self.plot = plot
		self.axes = axes
		self.canvas = self.axes.figure.canvas
		self.axes = None
		
		print "MOVER!"
		self.canvas.mpl_connect('scroll_event', self.mpl_scroll)
		self.last_x, self.last_y = None, None
		self.handles = []
		self.handles.append(self.canvas.mpl_connect('motion_notify_event', self.mouse_move))
		self.handles.append(self.canvas.mpl_connect('button_press_event', self.mouse_down))
		self.handles.append(self.canvas.mpl_connect('button_release_event', self.mouse_up))
		self.begin_x, self.begin_y = None, None
		self.moved = False
		self.zoom_queue = []
		self.zoom_counter = 0
		
	def disconnect_events(self):
		for handle in self.handles:
			self.canvas.mpl_disconnect(handle)
		
	def mouse_up(self, event):
		self.last_x, self.last_y = None, None
		if self.moved:
			self.plot.ranges = list(self.plot.ranges_show)
			self.plot.compute()
			self.plot.jobsManager.execute()
			self.moved = False
	
	def mouse_down(self, event):
		self.moved = False
		print event.button
		if event.dblclick:
			factor = 0.333
			if event.button != 1:
				factor = 1/factor
			self.plot.zoom(factor, axes=event.inaxes, x=event.xdata, y=event.ydata)
		else:
			self.begin_x, self.begin_y = event.xdata, event.ydata
			self.last_x, self.last_y = event.xdata, event.ydata
			self.current_axes = event.inaxes
			self.plot.ranges_begin = list(self.plot.ranges_show)
	
	def mouse_move(self, event):
		#return
		#print event.xdata, event.ydata, event.button
		#print event.key
		if self.last_x is not None and event.xdata is not None and self.current_axes is not None:
			#axes = event.inaxes
			transform = self.current_axes.transData.inverted().transform
			x_data, y_data = event.xdata, event.ydata
			self.moved = True
			dx = self.last_x - x_data
			dy = self.last_y - y_data 
			xmin, xmax = self.plot.ranges_show[self.current_axes.xaxis_index][0] + dx, self.plot.ranges_show[self.current_axes.xaxis_index][1] + dx
			if self.plot.dimensions == 1:
				ymin, ymax = self.plot.range_level[0] + dy, self.plot.range_level[1] + dy
			else:
				ymin, ymax = self.plot.ranges_show[self.current_axes.yaxis_index][0] + dy, self.plot.ranges_show[self.current_axes.yaxis_index][1] + dy
			#self.plot.ranges_show = [[xmin, xmax], [ymin, ymax]]
			self.plot.ranges_show[self.current_axes.xaxis_index] = [xmin, xmax]
			if self.plot.dimensions == 1:
				self.plot.range_level = [ymin, ymax]
			else:
				self.plot.ranges_show[self.current_axes.yaxis_index] = [ymin, ymax]
			# TODO: maybe the dimension should be stored in the axes, not in the plotdialog
			for axes in self.plot.getAxesList():
				if self.plot.dimensions == 1:
					# ftm we assume we only have 1 histogram, meabning axes == self.current_axes
					axes.set_xlim(*self.plot.ranges_show[self.current_axes.xaxis_index])
					axes.set_ylim(*self.plot.range_level)
				else:
					if axes.xaxis_index == self.current_axes.xaxis_index:
						axes.set_xlim(*self.plot.ranges_show[self.current_axes.xaxis_index])
					if axes.yaxis_index == self.current_axes.xaxis_index:
						axes.set_ylim(*self.plot.ranges_show[self.current_axes.xaxis_index])
					if axes.xaxis_index == self.current_axes.yaxis_index:
						axes.set_xlim(*self.plot.ranges_show[self.current_axes.yaxis_index])
					if axes.yaxis_index == self.current_axes.yaxis_index:
						axes.set_ylim(*self.plot.ranges_show[self.current_axes.yaxis_index])

			# transform again after we changed the axes limits
			transform = self.current_axes.transData.inverted().transform
			x_data, y_data = transform([event.x*1., event.y*1])
			self.last_x, self.last_y = x_data, y_data
				
			self.canvas.draw_idle()

		
		
	def mpl_scroll(self, event):
		print event.xdata, event.ydata, event.step
		factor = 10**(-event.step/8)
		self.zoom_counter += 1
		
		print dir(event)
		if factor < 1:
			self.plot.zoom(factor, event.inaxes, event.xdata, event.ydata)
			#self.zoom_queue.append((factor, event.xdata, event.ydata))
		else:
			self.plot.zoom(factor, event.inaxes, event.xdata, event.ydata) #, event.xdata, event.ydata)
			#self.zoom_queue.append((factor, None, None))
		return
		def idle_zoom(ignore=None, zoom_counter=None, axes=None):
			
			if zoom_counter < self.zoom_counter:
				pass # ignore, a later event will come
				print "ignored" * 30
			else:
				#zoom_queue = list((self.zoom_queue) # make copy to ensure it doesn't get modified in 
				for i, (factor, x, y) in enumerate(self.zoom_queue):
					# only redraw at last call
					is_last = i==len(self.zoom_queue)-1
					self.plot.zoom(factor, axes=axes, x=x, y=y, recalculate=False, history=False, redraw=is_last)
				self.zoom_queue = []
		if event.axes:
			QtCore.QTimer.singleShot(1, functools.partial(idle_zoom, zoom_counter=self.zoom_counter, axes=event.inaxes))
		#print repr(event)
		
		
		
		
		
		
class LinkButton(QtGui.QToolButton):
	def __init__(self, title, dataset, axisIndex, parent):
		super(LinkButton, self).__init__(parent)
		self.setToolTip("link this axes with others (experimental and unstable)")
		self.plot = parent
		self.dataset = dataset
		self.axisIndex = axisIndex
		self.setText(title)
		#self.setAcceptDrops(True)
		#self.disconnect_icon = QtGui.QIcon(iconfile('network-disconnect-2'))
		#self.connect_icon = QtGui.QIcon(iconfile('network-connect-3'))
		self.disconnect_icon = QtGui.QIcon(iconfile('link_break'))
		self.connect_icon = QtGui.QIcon(iconfile('link'))
		#self.setIcon(self.disconnect_icon)
		
		#self.action_link_global = QtGui.QAction(self.connect_icon, '&Global link', self)
		#self.action_unlink = QtGui.QAction(self.connect_icon, '&Unlink', self)
		#self.menu = QtGui.QMenu()
		#self.menu.addAction(self.action_link_global)
		#self.menu.addAction(self.action_unlink)
		#self.action_link_global.triggered.connect(self.onLinkGlobal)
		self.setToolTip("Link or unlink axis. When an axis is linked, changing an axis (like zooming) will update all axis of plots that have the same (and linked) axis.")
		self.setToolButtonStyle(QtCore.Qt.ToolButtonIconOnly)
		self.setIcon(self.disconnect_icon)
		#self.setDefaultAction(self.action_link_global)
		self.setCheckable(True)
		self.setChecked(False)
		self.clicked.connect(self.onToggleLink)
		#self.setMenu(self.menu)
		self.link = None

	def onToggleLink(self):
		if self.isChecked():
			logger.debug("connected link")
			self.link = self.dataset.link(self.plot.expressions[self.axisIndex], self)
			self.setIcon(self.connect_icon)
		else:
			logger.debug("disconnecting link")
			self.dataset.unlink(self.link, self)
			self.link = None
			self.setIcon(self.disconnect_icon)

	def onLinkGlobal(self):
		self.link = self.dataset.link(self.plot.expressions[self.axisIndex], self)
		logger.debug("made global link: %r" % self.link)
		#self.parent.links[self.axisIndex] = self.linkHandle
		
	def onChangeRangeShow(self, range_):
		logger.debug("received range show change for plot=%r, axisIndex %r, range=%r" % (self.plot, self.axisIndex, range_))
		self.plot.ranges_show[self.axisIndex] = range_
		
	def onChangeRange(self, range_):
		logger.debug("received range change for plot=%r, axisIndex %r, range=%r" % (self.plot, self.axisIndex, range_))
		self.plot.ranges[self.axisIndex] = range_
		
	def onCompute(self):
		logger.debug("received compute for plot=%r, axisIndex %r" % (self.plot, self.axisIndex))
		self.plot.compute()
	
	def onPlot(self):
		logger.debug("received plot command for plot=%r, axisIndex %r" % (self.plot, self.axisIndex))
		self.plot.plot()
	
	def onLinkLimits(self, min, max):
		self.plot.expressions[self.axisIndex] = expression
	
	def onChangeExpression(self, expression):
		logger.debug("received change expression for plot=%r, axisIndex %r, expression=%r" % (self.plot, self.axisIndex, expression))
		self.plot.expressions[self.axisIndex] = expression
		self.plot.axisboxes[self.axisIndex].lineEdit().setText(expression)
		
		

	def _dragEnterEvent(self, e):
		print e.mimeData()
		print e.mimeData().text()
		if e.mimeData().hasFormat('text/plain'):
			e.accept()
			
		else:
			e.ignore() 
			
	def dropEvent(self, e):
		position = e.pos()        
		#self.button.move(position)
		print "do", e.mimeData().text()
		e.setDropAction(QtCore.Qt.MoveAction)
		e.accept()

	def _mousePressEvent(self, e):
		
			super(LinkButton, self).mousePressEvent(e)
			
			if e.button() == QtCore.Qt.LeftButton:
				print 'press'			

	def _mouseMoveEvent(self, e):
		if e.buttons() != QtCore.Qt.LeftButton:
			return

		mimeData = QtCore.QMimeData()

		drag = QtGui.QDrag(self)
		drag.setMimeData(mimeData)
		drag.setHotSpot(e.pos() - self.rect().topLeft())
		mimeData.setText("blaat")

		dropAction = drag.start(QtCore.Qt.MoveAction)


class Queue(object):
	def __init__(self, name, default_delay, default_callable):
		self.name = name
		self.default_delay = default_delay
		self.counter = 0
		self.default_callable = default_callable
		
		
	def __call__(self, callable=None, delay=None, *args, **kwargs):
		delay = delay or self.default_delay
		callable = callable or self.default_callable
		def call(ignore=None, counter=None, callable=None):
			if counter < self.counter:
				pass # ignore, more events coming
			else:
				#print ("CALL " + self.name + " ") * 100
				callable()
		callable = functools.partial(callable, *args, **kwargs)
		self.counter += 1
		print "add in queue", self.name, delay
		QtCore.QTimer.singleShot(delay, functools.partial(call, counter=self.counter, callable=callable))

class PlotDialog(QtGui.QDialog):
	def addAxes(self):
		self.axes = self.fig.add_subplot(111)
		self.axes.xaxis_index = 0
		if self.dimensions > 1:
			self.axes.yaxis_index = 1
		self.axes.hold(True)
		
	def getAxesList(self):
		return [self.axes]
	
	def __repr__(self):
		return "<%s at 0x%x expr=%r>" % (self.__class__.__name__, id(self), self.expressions) 
	
	def plug_toolbar(self, callback, order):
		self.plugin_queue_toolbar.append((callback, order))
		
	def plug_page(self, callback, pagename, pageorder, order):
		self.plugin_queue_page.append((callback, pagename, pageorder, order))

	def plug_grids(self, callback_define, callback_draw):
		self.plugin_grids_defines.append(callback_define)
		self.plugin_grids_draw.append(callback_draw)

	def get_options(self):
		options = collections.OrderedDict()
		options["type-names"] = map(str.strip, self.names.split(","))
 		options["expressions"] = self.expressions
		options["amplitude_expression"] = self.amplitude_expression
		options["ranges"] = self.ranges
		options["ranges_show"] = self.ranges_show
		options["grid_size"] = self.grid_size
		options["vector_grid_size"] = self.vector_grid_size
		return dict(options)

	def apply_options(self, options):
		#map = {"expressions",}
		recognize = "expressions amplitude_expression ranges ranges_show grid_size vector_grid_size".split()
		for key in recognize:
			if key in self.options:
				setattr(self, key, options[key])
		for key in options.keys():
			if key not in recognize:
				logger.error("option %s not recognized, ignored" % key)
		self.queue_update()

	def __init__(self, parent, jobsManager, dataset, expressions, axisnames, width=5, height=4, dpi=100, **options):
		super(PlotDialog, self).__init__(parent)
		print "aap"
		self.options = options

		if "fraction" in self.options:
			dataset.setFraction(float(self.options["fraction"]))
		
		self.undoManager = parent.undoManager
		self.setWindowTitle(dataset.name)
		self.jobsManager = jobsManager
		self.dataset = dataset
		self.axisnames = axisnames
		self.pool = ThreadPool()
		self.expressions = expressions
		self.dimensions = len(self.expressions)
		self.grids = Grids(self.dataset, self.pool, *self.expressions)

		# create plugins
		self.plugin_grids_defines = []
		self.plugin_grids_draw = []
		self.plugin_queue_toolbar = [] # list of tuples (callback, order)
		self.plugin_queue_page = []
		print gavi.vaex.plugin.PluginPlot.registry
		print "$" * 200
		print self.__class__, gavi.vaex.plugin.transferfunction.TransferFunctionPlugin.useon(self.__class__)
		self.plugins = [cls(self) for cls in gavi.vaex.plugin.PluginPlot.registry if cls.useon(self.__class__)]
		self.plugins_map = {plugin.name:plugin for plugin in self.plugins}
		#self.plugin_zoom = plugin.zoom.ZoomPlugin(self)
		
		self.vector_grid_size = eval(self.options.get("vector_grid_size", "16"))


		if self.dimensions == 3:
			self.resize(800+400,700)
		else:
			self.resize(800,700)


		self.colormap = "PaulT_plusmin" #"binary"
		self.colormap_vector = "binary"

		self.colormap = "PaulT_plusmin" #"binary"
		self.colormap_vector = "binary"

		self.aspect = None
		self.axis_lock = False

		self.update_counter = 0
		self.t_0 = 0
		self.t_last = 0

		self.shortcuts = []


		self.grid_size = eval(self.options.get("grid_size", "512/2"))
		self.xoffset, self.yoffset = 0, 0
		self.show_disjoined = False

		self.fig = Figure(figsize=(width, height), dpi=dpi)
		self.addAxes()

		self.canvas =  FigureCanvas(self.fig)
		self.canvas.setParent(self)

		self.queue_update = Queue("update", 1000, self.update_direct)
		self.queue_redraw = Queue("redraw", 5, self.canvas.draw)
		self.queue_replot = Queue("replot", 10, self.plot)

		self.layout_main = QtGui.QVBoxLayout()
		self.layout_content = QtGui.QHBoxLayout()
		self.layout_main.setContentsMargins(0, 0, 0, 0)
		self.layout_content.setContentsMargins(0, 0, 0, 0)
		self.layout_main.setSpacing(0)
		self.layout_content.setSpacing(0)

		#self.button_layout.setSpacing(0)

		self.boxlayout = QtGui.QVBoxLayout()
		self.boxlayout_right = QtGui.QVBoxLayout()
		self.boxlayout.setContentsMargins(0, 0, 0, 0)
		self.boxlayout_right.setContentsMargins(0, 0, 0, 0)

		self.ranges = [None for _ in range(self.dimensions)] # min/max for the data
		self.ranges_show = [None for _ in range(self.dimensions)] # min/max for the plots
		self.range_level = None

		self.ranges_previous = None
		self.ranges_show_previous = None
		self.ranges_level_previous = None


		#self.xmin_show, self.xmax_show = None, None
		#self.ymin_show, self.ymax_show = None, None
		#self.xmin, self.xmax = None, None
		#self.ymin, self.ymax = None, None
		self.currentModes = None
		self.lastAction = None

		self.beforeCanvas(self.layout_main)
		self.layout_main.addLayout(self.layout_content, 1.)
		self.layout_plot_region = QtGui.QHBoxLayout()
		self.layout_plot_region.addWidget(self.canvas, 1)

		self.boxlayout.addLayout(self.layout_plot_region, 1)
		self.addToolbar2(self.layout_main)
		self.afterCanvas(self.boxlayout_right)
		self.layout_content.addLayout(self.boxlayout, 1.)

		self.status_bar = QtGui.QStatusBar(self)
		self.layout_main.addWidget(self.status_bar)

		self.layout_content.addLayout(self.boxlayout_right, 0)
		self.setLayout(self.layout_main)

		self.compute_counter = 1 # to avoid reentrant 'computes'
		self.compute()
		self.jobsManager.after_execute.append(self.plot)
		#self.plot()
		FigureCanvas.setSizePolicy(self,
									QtGui.QSizePolicy.Expanding,
									QtGui.QSizePolicy.Expanding)
		FigureCanvas.updateGeometry(self)
		self.currentMode = None
		self.dataset.mask_listeners.append(self.onSelectMask)
		self.dataset.row_selection_listeners.append(self.onSelectRow)
		self.dataset.serie_index_selection_listeners.append(self.onSerieIndexSelect)
		self.shortcuts = []
		print "noot"
		self.grabGesture(QtCore.Qt.PinchGesture);
		self.grabGesture(QtCore.Qt.PanGesture);
		self.grabGesture(QtCore.Qt.SwipeGesture);

		self.signal_samp_send_selection = gavi.events.Signal("samp send selection")

		self.canvas.mpl_connect('resize_event', self.on_resize_event)
		#self.pinch_ranges_show = [None for i in range(self.dimension)]




	def on_resize_event(self, event):
		if not self.action_mini_mode_ultra.isChecked():
			self.fig.tight_layout()
			self.queue_redraw()
			print "tight layout"

	def event(self, event):
		if isinstance(event, QtGui.QGestureEvent):
			print event.activeGestures()
			for gesture in event.activeGestures():
				if isinstance(gesture, QtGui.QPinchGesture):
					center = gesture.centerPoint()
					print "center", center.x(), center.y(), gesture.totalScaleFactor(), gesture.scaleFactor()
					x, y =  center.x(), center.y()
					geometry = self.canvas.geometry()
					if geometry.contains(x, y):
						rx = x - geometry.x()
						ry = y - geometry.y()
						#nx, ny = rx/geometry.width(), y/geometry.height()
						transform = self.axes.transData.inverted().transform
						x_data, y_data = transform([rx, geometry.height()-1-ry])
						if gesture.lastScaleFactor() != 0:
							scale = (gesture.scaleFactor()/gesture.lastScaleFactor())
						else:
							scale = (gesture.scaleFactor())
						#@scale = gesture.totalScaleFactor()
						#print "ZOOM " * 100
						print rx, ry, x_data, y_data, scale
						scale = 1/(scale)
						self.zoom(scale, self.axes, x_data, y_data) # TODO: support for multiple axes
						#print dx, dy
			return True
		else:
			return super(PlotDialog, self).event(event)
			#print event, type(event)
			#return True


	def closeEvent(self, event):
		# disconnect this event, otherwise we get an update/redraw for nothing
		# since closing a dialog causes this event to fire otherwise
		self.parent().plot_dialogs.remove(self)
		self.pool.close()
		for axisbox, func in zip(self.axisboxes, self.onExpressionChangedPartials):
			axisbox.lineEdit().editingFinished.disconnect(func)
		self.dataset.mask_listeners.remove(self.onSelectMask)
		self.dataset.row_selection_listeners.remove(self.onSelectRow)
		self.dataset.serie_index_selection_listeners.remove(self.onSerieIndexSelect)
		self.jobsManager.after_execute.remove(self.plot)
		#self.action_play_stop.setChecked(False)
		super(PlotDialog, self).closeEvent(event)
		print "close event"

	def onSerieIndexSelect(self, serie_index):
		pass

	def getExpressionList(self):
		return self.dataset.column_names

	def add_pages(self, toolbox):
		pass


	def afterCanvas(self, layout):

		layout.setContentsMargins(0, 0, 0, 0)
		layout.setSpacing(0)

		self.bottomFrame = QtGui.QFrame(self)
		layout.addWidget(self.bottomFrame, 0)
		self.toolbox = QtGui.QToolBox(self.bottomFrame)
		self.toolbox.setMinimumWidth(250)

		self.bottom_layout = QtGui.QVBoxLayout()
		self.bottomFrame.setLayout(self.bottom_layout)
		self.bottom_layout.addWidget(self.toolbox)


		self.plug_page(self.page_main, "Main", 1., 1.)
		self.plug_page(self.page_vector, "Vector field", 2., 1.)
		self.plug_page(self.page_display, "Display", 3., 1.)

		# first get unique page orders
		pageorders = {}
		for callback, pagename, pageorder, order in self.plugin_queue_page:
			pageorders[pagename] = pageorder
		self.pages = {}
		for pagename, order in sorted(pageorders.items(), key=itemgetter(1)):
			page_frame = QtGui.QFrame(self)
			self.pages[pagename] = page_frame
			self.toolbox.addItem(page_frame, pagename)
			logger.debug("created page: "+pagename)
		for pagename, order in sorted(pageorders.items(), key=itemgetter(1)):
			logger.debug("filling page: %sr %r" % (pagename, filter(lambda x: x[1] == pagename, self.plugin_queue_page)))
			for callback, pagename_, pageorder, order in sorted(filter(lambda x: x[1] == pagename, self.plugin_queue_page), key=itemgetter(3)):
	 			logger.debug("filling page: "+pagename +" order=" +str(order) + " callback=" +str(callback))
				callback(self.pages[pagename])
		page_name = self.options.get("page", "Main")
		page_frame = self.pages.get(page_name, None)
		if page_frame:
			self.toolbox.setCurrentWidget(page_frame)


	def page_main(self, page):
		print "page main"
		self.frame_options_main = page #QtGui.QFrame(self)
		self.layout_frame_options_main =  QtGui.QVBoxLayout()
		self.frame_options_main.setLayout(self.layout_frame_options_main)
		self.layout_frame_options_main.setSpacing(0)
		self.layout_frame_options_main.setContentsMargins(0,0,0,0)
		self.layout_frame_options_main.setAlignment(QtCore.Qt.AlignTop)

		self.button_layout = QtGui.QVBoxLayout()
		if self.dimensions > 1:
			self.buttonFlipXY = QtGui.QPushButton("exchange x and y")
			def flipXY():
				self.expressions.reverse()
				self.ranges.reverse()
				self.ranges_show.reverse()
				for box, expr in zip(self.axisboxes, self.expressions):
					box.lineEdit().setText(expr)
				self.compute()
				self.jobsManager.execute()
			self.buttonFlipXY.clicked.connect(flipXY)
			self.button_layout.addWidget(self.buttonFlipXY, 0.)
			self.buttonFlipXY.setAutoDefault(False)
			self.button_flip_colormap = QtGui.QPushButton("exchange colormaps")
			def flip_colormap():
				index1 = self.colormap_box.currentIndex()
				index2 = self.colormap_vector_box.currentIndex()
				self.colormap_box.setCurrentIndex(index2)
				self.colormap_vector_box.setCurrentIndex(index1)
			self.button_flip_colormap.clicked.connect(flip_colormap)
			self.button_layout.addWidget(self.button_flip_colormap)
			self.button_flip_colormap.setAutoDefault(False)
		self.layout_frame_options_main.addLayout(self.button_layout, 0)

		self.axisboxes = []
		self.onExpressionChangedPartials = []
		axisIndex = 0

		self.grid_layout = QtGui.QGridLayout()
		self.grid_layout.setColumnStretch(2, 1)
		#row = 0
		self.linkButtons = []
		for axisname in self.axisnames:
			row = axisIndex
			axisbox = QtGui.QComboBox(self)
			axisbox.setEditable(True)
			axisbox.setMinimumContentsLength(10)
			#self.form_layout.addRow(axisname + '-axis:', axisbox)
			self.grid_layout.addWidget(QtGui.QLabel(axisname + '-axis:', self), row, 1)
			self.grid_layout.addWidget(axisbox, row, 2, QtCore.Qt.AlignLeft)
			linkButton = LinkButton("link", self.dataset, axisIndex, self)
			self.linkButtons.append(linkButton)
			linkButton.setChecked(True)
			linkButton.setVisible(False)
			# obove doesn't fire event, do manually
			#linkButton.onToggleLink()
			if 1:
				functionButton = QtGui.QToolButton(self)
				functionButton.setIcon(QtGui.QIcon(iconfile('edit-mathematics')))
				menu = QtGui.QMenu()
				functionButton.setMenu(menu)
				functionButton.setPopupMode(QtGui.QToolButton.InstantPopup)
				#link_action = QtGui.QAction(QtGui.QIcon(iconfile('network-connect-3')), '&Link axis', self)
				#unlink_action = QtGui.QAction(QtGui.QIcon(iconfile('network-disconnect-2')), '&Unlink axis', self)
				templates = ["log(%s)", "sqrt(%s)", "1/(%s)", "abs(%s)"]

				for template in templates:
					action = QtGui.QAction(template % "...", self)
					def add(checked=None, axis_index=axisIndex, template=template):
						logger.debug("adding template %r to axis %r" % (template, axis_index))
						expression = self.expressions[axis_index].strip()
						if "#" in expression:
							expression = expression[:expression.index("#")].strip()
						self.expressions[axis_index] = template % expression
						self.axisboxes[axis_index].lineEdit().setText(self.expressions[axis_index])
						self.ranges[axis_index] = None
						if not self.axis_lock:
							self.ranges_show[axis_index] = None
						self.compute()
						self.jobsManager.execute()
					action.triggered.connect(add)
					menu.addAction(action)
				self.grid_layout.addWidget(functionButton, row, 3, QtCore.Qt.AlignLeft)
				#menu.addAction(unlink_action)
				#self.grid_layout.addWidget(functionButton, row, 2)
			#self.grid_layout.addWidget(linkButton, row, 0)
			#if axisIndex == 0:
			extra_expressions = []
			expressionList = self.getExpressionList()
			for prefix in ["", "v", "v_"]:
				names = "x y z".split()
				allin = True
				for name in names:
					if prefix + name not in expressionList:
						allin = False
				# if all items found, add it
				if allin:
					expression = "l2(%s) # l2 norm" % (",".join([prefix+name for name in names]))
					extra_expressions.append(expression)

				if 0: # this gives too much clutter
					for name1 in names:
						for name2 in names:
							if name1 != name2:
								if name1 in expressionList and name2 in expressionList:
									expression = "d(%s)" % (",".join([prefix+name for name in [name1, name2]]))
									extra_expressions.append(expression)


			axisbox.addItems(extra_expressions + self.getExpressionList())
			#axisbox.setCurrentIndex(self.expressions[axisIndex])
			#axisbox.currentIndexChanged.connect(functools.partial(self.onAxis, axisIndex=axisIndex))
			axisbox.lineEdit().setText(self.expressions[axisIndex])
			# keep a list to be able to disconnect
			self.onExpressionChangedPartials.append(functools.partial(self.onExpressionChanged, axisIndex=axisIndex))
			axisbox.lineEdit().editingFinished.connect(self.onExpressionChangedPartials[axisIndex])
			# if the combox pulldown is clicked, execute the same command
			axisbox.currentIndexChanged.connect(lambda _, axisIndex=axisIndex: self.onExpressionChangedPartials[axisIndex]())
			axisIndex += 1
			self.axisboxes.append(axisbox)
		row += 1
		self.layout_frame_options_main.addLayout(self.grid_layout, 0)
		#self.layout_frame_options_main.addLayout(self.form_layout, 0) # TODO: form layout can be removed?

		self.amplitude_box = QtGui.QComboBox(self)
		self.amplitude_box.setEditable(True)
		if "amplitude" in self.options:
			self.amplitude_box.addItems([self.options["amplitude"]])
		self.amplitude_box.addItems(["log(counts) if weighted is None else average", "counts", "counts**2", "sqrt(counts)"])
		self.amplitude_box.addItems(["log(counts+1)"])
		self.amplitude_box.addItems(["gf(log(counts+1),1) # gaussian filter"])
		self.amplitude_box.addItems(["gf(log(counts+1),2) # gaussian filter with higher sigma" ])
		self.amplitude_box.addItems(["counts/peak_columns # divide by peak value in every row"])
		self.amplitude_box.addItems(["counts/sum_columns # normalize columns"])
		self.amplitude_box.addItems(["counts/peak_rows # divide by peak value in every row"])
		self.amplitude_box.addItems(["counts/sum_rows # normalize rows"])
		self.amplitude_box.addItems(["log(counts/peak_columns)"])
		self.amplitude_box.addItems(["log(counts/sum_columns)"])
		self.amplitude_box.addItems(["log(counts/peak_rows)"])
		self.amplitude_box.addItems(["log(counts/sum_rows)"])
		self.amplitude_box.addItems(["abs(fft.fftshift(fft.fft2(counts))) # 2d fft"])
		self.amplitude_box.addItems(["abs(fft.fft(counts, axis=1)) # ffts along y axis"])
		self.amplitude_box.addItems(["abs(fft.fft(counts, axis=0)) # ffts along x axis"])
		self.amplitude_box.setMinimumContentsLength(10)
		self.grid_layout.addWidget(QtGui.QLabel("amplitude="), row, 1)
		self.grid_layout.addWidget(self.amplitude_box, row, 2, QtCore.Qt.AlignLeft)
		#self.amplitude_box.lineEdit().editingFinished.connect(self.onAmplitudeExpr)
		#self.amplitude_box.currentIndexChanged.connect(lambda _: self.onAmplitudeExpr())
		def onchange(*args, **kwargs):
			print "change:", args, kwargs
			self.onAmplitudeExpr()
		def onchange_line(*args, **kwargs):
			print "change: line", args, kwargs
			if len(str(self.amplitude_box.lineEdit().text())) == 0:
				self.onAmplitudeExpr()
		#self.amplitude_box.currentIndexChanged.connect(functools.partial(onchange, event="currentIndexChanged"))
		#self.amplitude_box.editTextChanged.connect(functools.partial(onchange, event="editTextChanged"))
		#self.amplitude_box.lineEdit().editingFinished.connect(functools.partial(onchange, event="editingFinished"))

		# this event is also fired when the line edit is finished, except when an empty entry is given
		self.amplitude_box.currentIndexChanged.connect(onchange)
		self.amplitude_box.lineEdit().editingFinished.connect(functools.partial(onchange_line, event="editingFinished"))


		self.amplitude_expression = str(self.amplitude_box.lineEdit().text())

		row += 1

		if self.dimensions > 1:
			process_colormaps()
			self.colormap_box = QtGui.QComboBox(self)
			self.colormap_box.setIconSize(QtCore.QSize(16, 16))
			model = QtGui.QStandardItemModel(self.colormap_box)
			for colormap_name in colormaps:
				colormap = matplotlib.cm.get_cmap(colormap_name)
				pixmap = colormap_pixmap[colormap_name]
				icon = QtGui.QIcon(pixmap)
				item = QtGui.QStandardItem(icon, colormap_name)
				model.appendRow(item)
			self.colormap_box.setModel(model);
			#self.form_layout.addRow("colormap=", self.colormap_box)
			self.grid_layout.addWidget(QtGui.QLabel("colormap="), row, 1)
			self.grid_layout.addWidget(self.colormap_box, row, 2, QtCore.Qt.AlignLeft)
			def onColorMap(index):
				colormap_name = str(self.colormap_box.itemText(index))
				logger.debug("selected colormap: %r" % colormap_name)
				self.colormap = colormap_name
				if hasattr(self, "widget_volume"):
					self.plugins_map["transferfunction"].tool.colormap = self.colormap
					self.plugins_map["transferfunction"].tool.update()
					self.widget_volume.colormap_index = index
					self.widget_volume.update()
				self.plot()
			cmapnames = "cmap colormap colourmap".split()
			if not set(cmapnames).isdisjoint(self.options):
				for name in cmapnames:
					if name in self.options:
						break
				cmap = self.options[name]
				if cmap not in colormaps:
					colormaps_sorted = sorted(colormaps)
					colormaps_string = " ".join(colormaps_sorted)
					dialog_error(self, "Wrong colormap name", "colormap {cmap} does not exist, choose between: {colormaps_string}".format(**locals()))
					index = 0
				else:
					index = colormaps.index(cmap)
				self.colormap_box.setCurrentIndex(index)
				self.colormap = colormaps[index]
			self.colormap_box.currentIndexChanged.connect(onColorMap)

		row += 1

		self.title_box = QtGui.QComboBox(self)
		self.title_box.setEditable(True)
		self.title_box.addItems([""] + self.getTitleExpressionList())
		self.title_box.setMinimumContentsLength(10)
		self.grid_layout.addWidget(QtGui.QLabel("title="), row, 1)
		self.grid_layout.addWidget(self.title_box, row, 2)
		self.title_box.lineEdit().editingFinished.connect(self.onTitleExpr)
		self.title_box.currentIndexChanged.connect(lambda _: self.onTitleExpr())
		self.title_expression = str(self.title_box.lineEdit().text())
		row += 1

		self.weight_box = QtGui.QComboBox(self)
		self.weight_box.setEditable(True)
		self.weight_box.addItems([self.options.get("weight", "")] + self.getExpressionList())
		self.weight_box.setMinimumContentsLength(10)
		self.grid_layout.addWidget(QtGui.QLabel("weight="), row, 1)
		self.grid_layout.addWidget(self.weight_box, row, 2)
		self.weight_box.lineEdit().editingFinished.connect(self.onWeightExpr)
		self.weight_box.currentIndexChanged.connect(lambda _: self.onWeightExpr())
		self.weight_expression = str(self.weight_box.lineEdit().text())
		if len(self.weight_expression.strip()) == 0:
			self.weight_expression = None

	def page_display(self, page):

		self.frame_options_visuals = page#QtGui.QFrame(self)
		self.layout_frame_options_visuals =  QtGui.QVBoxLayout()
		self.frame_options_visuals.setLayout(self.layout_frame_options_visuals)
		self.layout_frame_options_visuals.setAlignment(QtCore.Qt.AlignTop)

		if self.dimensions > 1:
			if 0: # TODO: reimplement contrast
				self.action_group_constrast = QtGui.QActionGroup(self)
				self.action_image_contrast = QtGui.QAction(QtGui.QIcon(iconfile('contrast')), '&Contrast', self)
				self.action_image_contrast_auto = QtGui.QAction(QtGui.QIcon(iconfile('contrast')), '&Contrast', self)
				self.toolbar2.addAction(self.action_image_contrast)

				self.action_image_contrast.triggered.connect(self.onActionContrast)
				self.contrast_list = [self.contrast_none, functools.partial(self.contrast_none_auto, percentage=0.1) , functools.partial(self.contrast_none_auto, percentage=1), functools.partial(self.contrast_none_auto, percentage=5)]
			self.contrast = self.contrast_none

			if 1:
				self.slider_gamma = QtGui.QSlider(self)
				self.label_gamma = QtGui.QLabel("...", self.frame_options_visuals)
				self.layout_frame_options_visuals.addWidget(self.label_gamma)
				self.layout_frame_options_visuals.addWidget(self.slider_gamma)
				self.slider_gamma.setRange(-100, 100)
				self.slider_gamma.valueChanged.connect(self.onGammaChange)
				self.slider_gamma.setValue(0)
				self.slider_gamma.setOrientation(QtCore.Qt.Horizontal)
				#self.slider_gamma.setMaximumWidth(100)
			self.image_gamma = 1.
			self.update_gamma_label()

			self.image_invert = False
			#self.action_image_invert = QtGui.QAction(QtGui.QIcon(iconfile('direction')), 'Invert image', self)
			#self.action_image_invert.setCheckable(True)
			#self.action_image_invert.triggered.connect(self.onActionImageInvert)
			#self.toolbar2.addAction(self.action_image_invert)
			self.button_image_invert = QtGui.QPushButton(QtGui.QIcon(iconfile('direction')), 'Invert image', self.frame_options_visuals)
			self.button_image_invert.setCheckable(True)
			self.button_image_invert.setAutoDefault(False)
			self.button_image_invert.clicked.connect(self.onActionImageInvert)
			self.layout_frame_options_visuals.addWidget(self.button_image_invert)


	def create_slider(self, parent, label_text, value_min, value_max, getter, setter, value_steps=1000, format=" {0:<0.3f}", transform=lambda x: x, inverse=lambda x: x):
		label = QtGui.QLabel(label_text, parent)
		label_value = QtGui.QLabel(label_text, parent)
		slider = QtGui.QSlider(parent)
		slider.setOrientation(QtCore.Qt.Horizontal)
		slider.setRange(0, value_steps)

		def update_text():
			#label.setText("mean/sigma: {0:<0.3f}/{1:.3g} opacity: {2:.3g}".format(self.tool.function_means[i], self.tool.function_sigmas[i], self.tool.function_opacities[i]))
			label_value.setText(format.format(getter()))
		def on_change(index, slider=slider):
			value = index/float(value_steps) * (inverse(value_max) - inverse(value_min)) + inverse(value_min)
			print label_text, "set to", value, "(", inverse(value), ")"
			setter(transform(value))
			update_text()
		slider.setValue((inverse(getter()) - inverse(value_min))/(inverse(value_max) - inverse(value_min)	) * value_steps)
		update_text()
		slider.valueChanged.connect(on_change)
		return label, slider, label_value

	def create_checkbox(self, parent, label, getter, setter):
		checkbox = QtGui.QCheckBox(label, parent)
		checkbox.setChecked(getter())
		def stateChanged(state):
			value = state == QtCore.Qt.Checked
			setter(value)

		checkbox.stateChanged.connect(stateChanged)
		return checkbox

	def page_vector(self, page):
		self.frame_options_vector2d = page #QtGui.QFrame(self)
		self.layout_frame_options_vector2d =  QtGui.QVBoxLayout()
		self.frame_options_vector2d.setLayout(self.layout_frame_options_vector2d)
		self.layout_frame_options_vector2d.setSpacing(0)
		self.layout_frame_options_vector2d.setContentsMargins(0,0,0,0)
		self.layout_frame_options_vector2d.setAlignment(QtCore.Qt.AlignTop)

		self.grid_layout_vector = QtGui.QGridLayout()
		self.grid_layout_vector.setColumnStretch(2, 1)
		self.layout_frame_options_vector2d.addLayout(self.grid_layout_vector)

		row = 0

		self.vectors_subtract_mean = bool(eval(self.options.get("vsub_mean", "False")))
		def setter(value):
			self.vectors_subtract_mean = value
			self.plot()
		self.vector_subtract_mean_checkbox = self.create_checkbox(page, "subtract mean", lambda : self.vectors_subtract_mean, setter)
		self.grid_layout_vector.addWidget(self.vector_subtract_mean_checkbox, row, 2)
		row += 1

		self.vectors_color_code_3rd = bool(eval(self.options.get("vcolor_3rd", "True" if self.dimensions <=2 else "False")))
		def setter(value):
			self.vectors_color_code_3rd = value
			self.plot()
		self.vectors_color_code_3rd_checkbox = self.create_checkbox(page, "color code 3rd axis", lambda : self.vectors_color_code_3rd, setter)
		self.grid_layout_vector.addWidget(self.vectors_color_code_3rd_checkbox, row, 2)
		row += 1



		if self.dimensions > -1:
			self.weight_x_box = QtGui.QComboBox(self)
			self.weight_x_box.setMinimumContentsLength(10)
			self.weight_x_box.setEditable(True)
			self.weight_x_box.addItems([self.options.get("vx", "")] + self.getExpressionList())
			self.weight_x_box.setMinimumContentsLength(10)
			self.grid_layout_vector.addWidget(QtGui.QLabel("vx="), row, 1)
			self.grid_layout_vector.addWidget(self.weight_x_box, row, 2)
			#def onWeightXExprLine(*args, **kwargs):
			#	if len(str(self.weight_x_box.lineEdit().text())) == 0:
			#		self.onWeightXExpr()
			self.weight_x_box.lineEdit().editingFinished.connect(lambda _=None: self.onWeightXExpr())
			self.weight_x_box.currentIndexChanged.connect(lambda _=None: self.onWeightXExpr())
			self.weight_x_expression = str(self.weight_x_box.lineEdit().text())
			if 0:
				for name in "x y z".split():
					if name in self.expressions[0]:
						for prefix in "v v_".split():
							expression = (prefix+name)
							if expression in self.getExpressionList():
								self.weight_x_box.lineEdit().setText(expression)
								self.weight_x_expression = expression

			row += 1

			self.weight_y_box = QtGui.QComboBox(self)
			self.weight_y_box.setEditable(True)
			self.weight_y_box.addItems([self.options.get("vy", "")] + self.getExpressionList())
			self.weight_y_box.setMinimumContentsLength(10)
			self.grid_layout_vector.addWidget(QtGui.QLabel("vy="), row, 1)
			self.grid_layout_vector.addWidget(self.weight_y_box, row, 2)
			#def onWeightYExprLine(*args, **kwargs):
			#	if len(str(self.weight_y_box.lineEdit().text())) == 0:
			#		self.onWeightYExpr()
			self.weight_y_box.lineEdit().editingFinished.connect(lambda _=None: self.onWeightYExpr())
			self.weight_y_box.currentIndexChanged.connect(lambda _=None: self.onWeightYExpr())
			self.weight_y_expression = str(self.weight_y_box.lineEdit().text())
			if 0:
				for name in "x y z".split():
					if self.dimensions > 1:
						if name in self.expressions[1]:
							for prefix in "v v_".split():
								expression = (prefix+name)
								if expression in self.getExpressionList():
									self.weight_y_box.lineEdit().setText(expression)
									self.weight_y_expression = expression

			row += 1

			self.weight_z_box = QtGui.QComboBox(self)
			self.weight_z_box.setEditable(True)
			self.weight_z_box.addItems([self.options.get("vz", "")] + self.getExpressionList())
			self.weight_z_box.setMinimumContentsLength(10)
			self.grid_layout_vector.addWidget(QtGui.QLabel("vz="), row, 1)
			self.grid_layout_vector.addWidget(self.weight_z_box, row, 2)
			#def onWeightZExprLine(*args, **kwargs):
			#	if len(str(self.weight_z_box.lineEdit().text())) == 0:
			#		self.onWeightZExpr()
			self.weight_z_box.lineEdit().editingFinished.connect(lambda _=None: self.onWeightZExpr())
			self.weight_z_box.currentIndexChanged.connect(lambda _=None: self.onWeightZExpr())
			self.weight_z_expression = str(self.weight_z_box.lineEdit().text())

			row += 1

			self.colormap_vector_box = QtGui.QComboBox(self)
			self.colormap_vector_box.setIconSize(QtCore.QSize(16, 16))
			model = QtGui.QStandardItemModel(self.colormap_vector_box)
			for colormap_name in colormaps:
				colormap = matplotlib.cm.get_cmap(colormap_name)
				pixmap = colormap_pixmap[colormap_name]
				icon = QtGui.QIcon(pixmap)
				item = QtGui.QStandardItem(icon, colormap_name)
				model.appendRow(item)
			self.colormap_vector_box.setModel(model);
			#self.form_layout.addRow("colormap=", self.colormap_vector_box)
			self.grid_layout_vector.addWidget(QtGui.QLabel("vz_cmap="), row, 1)
			self.grid_layout_vector.addWidget(self.colormap_vector_box, row, 2, QtCore.Qt.AlignLeft)
			def onColorMap(index):
				colormap_name = str(self.colormap_vector_box.itemText(index))
				logger.debug("selected colormap for vector: %r" % colormap_name)
				self.colormap_vector = colormap_name
				self.plot()

			cmapnames = "vz_cmap vz_colormap vz_colourmap".split()
			if not set(cmapnames).isdisjoint(self.options):
				for name in cmapnames:
					if name in self.options:
						break
				cmap = self.options[name]
				if cmap not in colormaps:
					colormaps_sorted = sorted(colormaps)
					colormaps_string = " ".join(colormaps_sorted)
					dialog_error(self, "Wrong colormap name", "colormap {cmap} does not exist, choose between: {colormaps_string}".format(**locals()))
					index = 0
				else:
					index = colormaps.index(cmap)
				self.colormap_vector_box.setCurrentIndex(index)
				self.colormap_vector = colormaps[index]
			self.colormap_vector_box.currentIndexChanged.connect(onColorMap)

			row += 1

		#self.toolbox.addItem(self.frame_options_main, "Main")
		#self.toolbox.addItem(self.frame_options_vector2d, "Vector 2d")
		#self.toolbox.addItem(self.frame_options_visuals, "Display")
		#self.add_pages(self.toolbox)



		#self.form_layout = QtGui.QFormLayout()


		self.canvas.mpl_connect('motion_notify_event', self.onMouseMove)
		#self.setStatusBar(self.status_bar)
		#layout.setMargin(0)
		#self.grid_layout.setMargin(0)
		self.grid_layout.setHorizontalSpacing(0)
		self.grid_layout.setVerticalSpacing(0)
		self.grid_layout.setContentsMargins(0, 0, 0, 0)

		self.button_layout.setContentsMargins(0, 0, 0, 0)
		self.button_layout.setSpacing(0)
		self.bottom_layout.setContentsMargins(0, 0, 0, 0)
		self.bottom_layout.setSpacing(0)
		#self.form_layout.setContentsMargins(0, 0, 0, 0)
		#self.form_layout.setSpacing(0)
		self.grid_layout.setContentsMargins(0, 0, 0, 0)
		self.messages = {}
		#super(self.__class__, self).afterLayout()



		self.add_shortcut(self.action_fullscreen, "F")
		self.add_shortcut(self.action_toolbar_toggle, "T")
		self.add_shortcut(self.action_move, "M")
		self.add_shortcut(self.action_pick, "P")
		self.add_shortcut(self.action_mini_mode_normal, "C")
		self.add_shortcut(self.action_mini_mode_ultra, "U")
		self.add_shortcut(self.action_lasso, "L")
		self.add_shortcut(self.action_xrange, "x")
		self.add_shortcut(self.action_yrange, "y")
		self.add_shortcut(self.action_select_none, "n")
		self.add_shortcut(self.action_select_invert, "i")
		self.add_shortcut(self.action_select_mode_and, "&")
		self.add_shortcut(self.action_select_mode_or, "|")
		self.add_shortcut(self.action_select_mode_replace, "=")

		self.add_shortcut(self.action_undo, "Ctrl+Z")
		self.add_shortcut(self.action_redo, "Alt+Y")

		self.add_shortcut(self.action_display_mode_both, "1")
		self.add_shortcut(self.action_display_mode_full, "2")
		self.add_shortcut(self.action_display_mode_selection, "3")
		self.add_shortcut(self.action_display_mode_both_contour, "4")
		self.add_shortcut(self.action_res_1,"Alt+1")
		self.add_shortcut(self.action_res_2,"Alt+2")
		self.add_shortcut(self.action_res_3,"Alt+3")
		self.add_shortcut(self.action_res_4,"Alt+4")
		self.add_shortcut(self.action_res_5,"Alt+5")

		#if "zoom" in self.options:
		#	factor = eval(self.options["zoom"])
		#	self.zoom(factor)
		if "lim" in self.options:
			for i in range(self.dimensions):
				self.ranges[i] = eval(self.options["lim"])
		if "xlim" in self.options:
			self.ranges[0] = eval(self.options["xlim"])
		if "ylim" in self.options:
			self.ranges[1] = eval(self.options["ylim"])
		if "zlim" in self.options:
			self.ranges[2] = eval(self.options["zlim"])
		if "aspect" in self.options:
			self.aspect = eval(self.options["aspect"])
			self.action_aspect_lock_one.setChecked(True)
		if "compact" in self.options:
			value = self.options["compact"]
			if value in ["ultra", "+"]:
				self.action_mini_mode_ultra.trigger()
			else:
				self.action_mini_mode_normal.trigger()

		self.first_time = True
		self.checkUndoRedo()

	def add_shortcut(self, action, key):
		def trigger(action):
			def call(action=action):
				print "toggle"
				action.toggle()
				action.trigger()
			return call
		if action.isEnabled():
			print "key", key
			shortcut = QtGui.QShortcut(QtGui.QKeySequence(key), self)
			shortcut.activated.connect(trigger(action))
			self.shortcuts.append(shortcut)

	def checkUndoRedo(self):
		self.action_undo.setEnabled(self.undoManager.can_undo())
		if self.undoManager.can_undo():
			self.action_undo.setToolTip("Undo: "+self.undoManager.actions_undo[-1].description())

		self.action_redo.setEnabled(self.undoManager.can_redo())
		if self.undoManager.can_redo():
			self.action_redo.setToolTip("Redo: "+self.undoManager.actions_redo[0].description())

	def onActionUndo(self):
		logger.debug("undo")
		self.undoManager.undo()
		self.checkUndoRedo()

	def onActionRedo(self):
		logger.debug("redo")
		self.undoManager.redo()
		self.checkUndoRedo()

	def onMouseMove(self, event):
		x, y = event.xdata, event.ydata
		if x is not None:
			extra_text = self.getExtraText(x, y)
			if extra_text:
				self.message("x, y:  %5.4e %5.4e %s" % (x, y, extra_text), index=0)
			else:
				self.message("x, y:  %5.4e %5.4e" % (x, y), index=0)
		else:
			self.message(None)

	def getExtraText(self, x, y):
		if hasattr(self, "counts"):
			if len(self.counts.shape) == 1:
				if self.ranges[0]:
					N = self.counts.shape[0]
					xmin, xmax = self.ranges[0]
					index = (x-xmin)/(xmax-xmin) * N
					if index >= 0 and index < N:
						return "value = %r" % (self.counts[index])
			if len(self.counts.shape) == 2:
				if self.ranges[0] and self.ranges[1]:
					Nx, Ny = self.counts.shape
					xmin, xmax = self.ranges[0]
					ymin, ymax = self.ranges[1]
					xindex = (x-xmin)/(xmax-xmin) * Nx
					yindex = (y-ymin)/(ymax-ymin) * Ny
					if xindex >= 0 and xindex < Nx and yindex >= 0 and yindex < Nx:
						return "value = %r" % (self.counts[xindex, yindex])


	def message(self, text, index=0):
		if text is None:
			if index in self.messages:
				del self.messages[index]
		else:
			self.messages[index] = text
		text = ""
		keys = self.messages.keys()
		keys.sort()
		text_parts = [self.messages[key] for key in keys]
		self.status_bar.showMessage(" | ".join(text_parts))


	def onWeightExpr(self):
		text = str(self.weight_box.lineEdit().text())
		print "############", self.weight_expression, text
		if (text == self.weight_expression) or (text == "" and self.weight_expression == None):
			logger.debug("same weight expression, will not update")
			return
		self.weight_expression = text
		print self.weight_expression
		if self.weight_expression.strip() == "":
			self.weight_expression = None
		self.range_level = None
		self.compute()
		self.jobsManager.execute()
		#self.plot()

	def onTitleExpr(self):
		self.title_expression = str(self.title_box.lineEdit().text())
		self.plot()

	def getTitleExpressionList(self):
		return []



	def onWeightXExpr(self):
		text = str(self.weight_x_box.lineEdit().text())
		if (text == self.weight_x_expression):
			logger.debug("same weight_x expression, will not update")
			return
		# is we set the text to "", check if some of the grids are existing, and simply 'disable' the and replot
		# otherwise check if it changed, if it did, see if we should do the grid computation, since
		# if only 1 grid is defined, we don't need it
		if text == "":
			self.weight_x_expression = ""
			if "weightx" in self.grids.grids:
				grid = self.grids.grids["weightx"]
				if grid is not None and grid.weight_expression is not None and len(grid.weight_expression) > 0:
					grid.weight_expression = ""
					self.plot()
					return

		self.weight_x_expression = text
		if self.weight_x_expression.strip() == "":
			self.weight_x_expression = None
		self.range_level = None
		self.check_vector_expressions()

	def check_vector_expressions(self):
		expressions = [self.weight_x_expression, self.weight_y_expression, self.weight_z_expression]
		non_none_expressions = [k for k in expressions if k is not None and len(k) > 0]
		if len(non_none_expressions) >= 2:
			self.compute()
			self.jobsManager.execute()
			#self.plot()


	def onWeightYExpr(self):
		text = str(self.weight_y_box.lineEdit().text())
		if (text == self.weight_y_expression):
			logger.debug("same weight_x expression, will not update")
			return
		# is we set the text to "", check if some of the grids are existing, and simply 'disable' the and replot
		# otherwise check if it changed, if it did, see if we should do the grid computation, since
		# if only 1 grid is defined, we don't need it
		if text == "":
			self.weight_y_expression = ""
			if "weighty" in self.grids.grids:
				grid = self.grids.grids["weighty"]
				if grid is not None and grid.weight_expression is not None and len(grid.weight_expression) > 0:
					grid.weight_expression = ""
					self.plot()
					return

		self.weight_y_expression = text
		if self.weight_y_expression.strip() == "":
			self.weight_y_expression = None
		self.range_level = None
		self.check_vector_expressions()

	def onWeightZExpr(self):
		text = str(self.weight_z_box.lineEdit().text())
		if (text == self.weight_z_expression):
			logger.debug("same weight_x expression, will not update")
			return
		# is we set the text to "", check if some of the grids are existing, and simply 'disable' the and replot
		# otherwise check if it changed, if it did, see if we should do the grid computation, since
		# if only 1 grid is defined, we don't need it
		if text == "":
			self.weight_z_expression = ""
			if "weightz" in self.grids.grids:
				grid = self.grids.grids["weightz"]
				if grid is not None and grid.weight_expression is not None and len(grid.weight_expression) > 0:
					grid.weight_expression = ""
					self.plot()
					return

		self.weight_z_expression = text
		if self.weight_z_expression.strip() == "":
			self.weight_z_expression = None
		self.range_level = None
		self.check_vector_expressions()

	def onAmplitudeExpr(self):
		text = str(self.amplitude_box.lineEdit().text())
		if len(text) == 0 or text == self.amplitude_expression:
			print "same expression, skip"
			return
		self.amplitude_expression = text
		print self.amplitude_expression
		self.range_level = None
		self.plot()

	def beforeCanvas(self, layout):
		self.addToolbar(layout) #, yselect=True, lasso=False)

	def onExpressionChanged(self, axisIndex):
		text = str(self.axisboxes[axisIndex].lineEdit().text())
		print "expr", repr(text)
		if text == self.expressions[axisIndex]:
			logger.debug("same expression, will not update")
			return
		self.expressions[axisIndex] = text
		# TODO: range reset as option?
		self.ranges[axisIndex] = None
		if not self.axis_lock:
			self.ranges_show[axisIndex] = None
		linkButton = self.linkButtons[axisIndex]
		link = linkButton.link
		if link:
			logger.debug("sending link messages")
			link.sendRanges(self.ranges[axisIndex], linkButton)
			link.sendRangesShow(self.ranges_show[axisIndex], linkButton)
			link.sendExpression(self.expressions[axisIndex], linkButton)
			gavi.dataset.Link.sendCompute([link], [linkButton])
		else:
			logger.debug("not linked")
		self.compute()
		self.jobsManager.execute()


	def compute(self):
		import traceback
		print "updating compute counter", ''.join(traceback.format_stack())
		compute_counter = self.compute_counter = self.compute_counter + 1
		t0 = time.time()


		def calculate_range(info, block, axisIndex):
			if compute_counter < self.compute_counter:
				print "STOP " * 100
				return True
			if info.error:
				print "error", info.error_text
				self.message(info.error_text, index=-1)
				return True
			subblock_size = math.ceil(len(block)/self.pool.nthreads)
			subblock_count = math.ceil(len(block)/subblock_size)
			def subblock(index):
				sub_i1, sub_i2 = index * subblock_size, (index +1) * subblock_size
				print "index", index, sub_i1, sub_i2, len(block)
				if len(block) < sub_i2: # last one can be a bit longer
					sub_i2 = len(block)
				return subspacefind.find_nan_min_max(block[sub_i1:sub_i2])
			#print "block", info.index, info.size, block
			self.message("min/max[%d] at %.1f%% (%.2fs)" % (axisIndex, info.percentage, time.time() - info.time_start), index=50+axisIndex )
			QtCore.QCoreApplication.instance().processEvents()
			if info.first:
				#self.ranges[axisIndex] = [np.nanmin(block), np.nanmax(block)]
				#pool.execute(
				results = self.pool.run_parallel(subblock)
				self.ranges[axisIndex] = min([result[0] for result in results]), max([result[1] for result in results])
				#self.ranges[axisIndex] = tuple(subspacefind.find_nan_min_max(block))
			else:
				results = self.pool.run_parallel(subblock)
				self.ranges[axisIndex] = min([self.ranges[axisIndex][0]] + [result[0] for result in results]), max([self.ranges[axisIndex][1]] + [result[1] for result in results])
				#xmin, xmax = tuple(subspacefind.find_nan_min_max(block))
				#self.ranges[axisIndex] = [min(self.ranges[axisIndex][0], xmin), max(self.ranges[axisIndex][1], xmax)]
				#self.ranges[axisIndex] = [min(self.ranges[axisIndex][0], np.nanmin(block)), max(self.ranges[axisIndex][1], np.nanmax(block)),]
			print "min/max for axis", axisIndex, self.ranges[axisIndex]
			if info.last:
				print "done with ranges", axisIndex, self.ranges[axisIndex]
				self.grids.ranges[axisIndex] = list(self.ranges[axisIndex])
				if self.ranges_show[axisIndex] is None:
					self.ranges_show[axisIndex] = self.ranges[axisIndex]
				self.message("min/max[%d] %.2fs" % (axisIndex, time.time() - t0), index=50+axisIndex)
				self.message(None, index=-1) # clear error msg

		for axisIndex in range(self.dimensions):
			print "axis", axisIndex, self.ranges[axisIndex]
			if self.ranges[axisIndex] is None:
				print "is None, so lets compute"
				self.jobsManager.addJob(0, functools.partial(calculate_range, axisIndex=axisIndex), self.dataset, self.expressions[axisIndex], **self.getVariableDict())
			else:
				self.grids.ranges[axisIndex] = list(self.ranges[axisIndex])
				if self.ranges_show[axisIndex] is None:
					self.ranges_show[axisIndex] = self.ranges[axisIndex]
		#if self.weight_expression is None or len(self.weight_expression.strip()) == 0:
		#	self.jobsManager.addJob(1, self.calculate_visuals, self.dataset, *self.expressions, **self.getVariableDict())
		#else:
		all_expressions = self.expressions + [self.weight_expression, self.weight_x_expression, self.weight_y_expression, self.weight_z_expression]
		self.grids.set_expressions(self.expressions)
		self.grids.define_grid("counts", self.grid_size, None)
		self.grids.define_grid("weighted", self.grid_size, self.weight_expression)
		self.grids.define_grid("weightx", self.vector_grid_size, self.weight_x_expression)
		self.grids.define_grid("weighty", self.vector_grid_size, self.weight_y_expression)
		self.grids.define_grid("weightz", self.vector_grid_size, self.weight_z_expression)
		for callback in self.plugin_grids_defines:
			callback(self.grids)
		self.grids.add_jobs(self.jobsManager)
		#self.jobsManager.addJob(1, functools.partial(self.calculate_visuals, compute_counter=compute_counter), self.dataset, *all_expressions, **self.getVariableDict())
		#for grid in self.grids:
		#	grid.add_

	def getVariableDict(self):
		playing = self.action_play_stop.isChecked()
		dict = {}
		if playing:
			dict["time"] = self.t_last = time.time() - self.t_0
		else:
			dict["time"] = self.t_last
		return dict

	def __getVariableDictMinMax(self):
		return {}

	def onSelectMask(self, mask):
		self.compute()
		#self.plot()

	def onSelectRow(self, row):
		print "row selected", row
		self.selected_point = None
		self.plot()


	def _beforeCanvas(self, layout):
		pass

	def _afterCanvas(self, layout):
		pass

	def setMode(self, action, force=False):
		print "set mode", action, action.text(), action.isChecked()
		#if not (action.isChecked() or force):
		if not action.isEnabled():
			logger.error("action selected that was disabled: %r" % action)
			self.setMode(self.lastAction)
			return
		if not (action.isChecked()):
			print "ignore action"
		else:
			self.lastAction = action
			axes_list = self.getAxesList()
			if self.currentModes is not None:
				print "disconnect", self.currentModes
				for mode in self.currentModes:
					mode.disconnect_events()
					mode.active = False
			useblit = True
			if action == self.action_move:
				self.currentModes = [Mover(self, axes) for axes in axes_list]
			if action == self.action_pick:
				#hasy = hasattr(self, "getdatay")
				#hasx = hasattr(self, "getdatax")
				#print "pick", hasx, hasy
				hasx = True
				hasy = len(self.expressions) > 1
				self.currentModes = [matplotlib.widgets.Cursor(axes, hasy, hasx, color="red", linestyle="dashed", useblit=useblit) for axes in axes_list]
				for cursor in self.currentModes:
					def onmove(event, current=cursor, cursors=self.currentModes):
						if event.inaxes:
							#print "on move", event.inaxes.xaxis_index, event.inaxes.yaxis_index
							for other_cursor in cursors:
								if current != other_cursor:
									other_cursor.onmove(event)
					cursor.connect_event('motion_notify_event', onmove)
				if hasx and hasy:
					for mode in self.currentModes:
						mode.connect_event('button_press_event', self.onPickXY)
				elif hasx:
					for mode in self.currentModes:
						mode.connect_event('button_press_event', self.onPickX)
				elif hasy:
					for mode in self.currentModes:
						mode.connect_event('button_press_event', self.onPickY)
				if useblit:
					self.canvas.draw() # buggy otherwise
			if action == self.action_xrange:
				logger.debug("setting last select action to xrange")
				self.lastActionSelect = self.action_xrange
				self.currentModes = [matplotlib.widgets.SpanSelector(axes, functools.partial(self.onSelectX, axes=axes), 'horizontal', useblit=useblit) for axes in axes_list]
				if useblit:
					self.canvas.draw() # buggy otherwise
			if action == self.action_yrange:
				logger.debug("setting last select action to yrange")
				self.lastActionSelect = self.action_yrange
				self.currentModes = [matplotlib.widgets.SpanSelector(axes, functools.partial(self.onSelectY, axes=axes), 'vertical', useblit=useblit) for axes in axes_list]
				if useblit:
					self.canvas.draw() # buggy otherwise
			if action == self.action_lasso:
				logger.debug("setting last select action to lasso")
				self.lastActionSelect = self.action_lasso
				self.currentModes =[ matplotlib.widgets.LassoSelector(axes, functools.partial(self.onSelectLasso, axes=axes)) for axes in axes_list]
				if useblit:
					self.canvas.draw() # buggy otherwise
			#self.plugin_zoom.setMode(action)
			for plugin in self.plugins:
				print "plugin", plugin, plugin.name
				plugin.setMode(action)
		self.syncToolbar()

		#if self.action_lasso
		#pass
		#self.


	def onPickX(self, event):
		x, y = event.xdata, event.ydata
		self.selected_point = None
		class Scope(object):
			pass
		# temp scope object
		scope = Scope()
		scope.index = None
		scope.distance = None
		def pick(block, info, scope=scope):
			if info.first:
				scope.index, scope.distance = find_nearest_index1d(block, x)
			else:
				scope.block_index, scope.block_distance = find_nearest_index1d(block, x)
				if scope.block_distance < scope.distance:
					scope.index = scope.block_index
		self.dataset.evaluate(pick, self.expressions[0], **self.getVariableDict())
		index, distance = scope.index, scope.distance
		print "nearest row", index, distance
		self.dataset.selectRow(index)
		self.setMode(self.lastAction)

	def onPickY(self, event):
		x, y = event.xdata, event.ydata
		self.selected_point = None
		class Scope(object):
			pass
		# temp scope object
		scope = Scope()
		scope.index = None
		scope.distance = None
		def pick(block, info, scope=scope):
			if info.first:
				scope.index, scope.distance = find_nearest_index1d(block, y)
			else:
				scope.block_index, scope.block_distance = find_nearest_index1d(block, y)
				if scope.block_distance < scope.distance:
					scope.index = scope.block_index
		self.dataset.evaluate(pick, self.expressions[1], **self.getVariableDict())
		index, distance = scope.index, scope.distance
		print "nearest row", index, distance
		self.dataset.selectRow(index)
		self.setMode(self.lastAction)



	def onPickXY(self, event):
		x, y = event.xdata, event.ydata
		wx = self.ranges_show[0][1] - self.ranges_show[0][0]
		wy = self.ranges_show[1][1] - self.ranges_show[1][0]

		self.selected_point = None
		class Scope(object):
			pass
		# temp scope object
		scope = Scope()
		scope.index = None
		scope.distance = None
		def pick(info, blockx, blocky, scope=scope):
			if info.first:
				scope.index, scope.distance = find_nearest_index(blockx, blocky, x, y, wx, wy)
			else:
				scope.block_index, scope.block_distance = find_nearest_index(blockx, blocky, x, y, wx, wy)
				if scope.block_distance < scope.distance:
					scope.index = scope.block_index
		self.dataset.evaluate(pick, *self.expressions[:2], **self.getVariableDict())
		index, distance = scope.index, scope.distance
		print "nearest row", index, distance
		self.dataset.selectRow(index)
		self.setMode(self.lastAction)


	def onSelectX(self, xmin, xmax, axes):
		#data = self.getdatax()
		x = [xmin, xmax]
		xmin, xmax = min(x), max(x)
		print "selectx", xmin, xmax
		#xmin = xmin if not self.useLogx() else 10**xmin
		#xmax = xmax if not self.useLogx() else 10**xmax
		#mask = np.zeros(self.dataset._length, dtype=np.bool)
		length = self.dataset.current_slice[1] - self.dataset.current_slice[0]
		mask = np.zeros(length, dtype=np.bool)
		#for block, info in self.dataset.evaluate(self.expressions[0]):
		#	mask[info.i1:info.i2] = (block >= xmin) & (block < xmax)
		#	print ">>>>>>>>>>>>>>> block", info.i1,info.i2, "selected", sum(mask[info.i1:info.i2])
		t0 = time.time()
		def putmask(info, block):
			self.message("selection at %.2f%% (%.1fs)" % (info.percentage, time.time() - t0), index=40 )
			QtCore.QCoreApplication.instance().processEvents()
			locals = {"block":block, "xmin":xmin, "xmax:":xmax}
			print info.__dict__
			#ne.evaluate("(block >= xmin) & (block < xmax)", out=mask[info.i1:info.i2], global_dict=locals)
			#range_check(block, mask[info.i1:info.i2], xmin, xmax)
			subspacefind.range_check(block, mask[info.i1:info.i2], xmin, xmax)
			#mask[info.i1:info.i2] = (block >= xmin) & (block < xmax)
			print ">> block x", info.i1,info.i2, "selected", np.sum(mask[info.i1:info.i2])
			mask[info.i1:info.i2] = self.select_mode(None if self.dataset.mask is None else self.dataset.mask[info.i1:info.i2], mask[info.i1:info.i2])
			if info.last:
				self.message("selection %.2fs" % (time.time() - t0), index=40)

		print "selectx", xmin, xmax, "selected", np.sum(mask), "for axis index", axes.xaxis_index

		# xaxis is stored in the matplotlib object
		self.dataset.evaluate(putmask, self.expressions[axes.xaxis_index], **self.getVariableDict())

		action = undo.ActionMask(self.undoManager, "select x range[%f,%f]" % (xmin, xmax), mask, self.applyMask)
		action.do()
		self.checkUndoRedo()

	def applyMask(self, mask):
		self.dataset.selectMask(mask)
		self.jobsManager.execute()
		self.setMode(self.lastAction)

	def onSelectY(self, ymin, ymax, axes):
		y = [ymin, ymax]
		ymin, ymax = min(y), max(y)
		#mask = (data >= ymin) & (data < ymax)
		mask = np.zeros(self.dataset._length, dtype=np.bool)
		def putmask(info, block):
			mask[info.i1:info.i2] = self.select_mode(None if self.dataset.mask is None else self.dataset.mask[info.i1:info.i2], (block >= ymin) & (block < ymax))
		self.dataset.evaluate(putmask, self.expressions[axes.yaxis_index], **self.getVariableDict())
		#for block, info in self.dataset.evaluate(self.expressions[1]):
		#	mask[info.i1:info.i2] = (block >= ymin) & (block < ymax)
		print "selecty", ymin, ymax, "selected", np.sum(mask)
		#self.dataset.selectMask(mask)
		#self.jobsManager.execute()
		#self.setMode(self.lastAction)
		action = undo.ActionMask(self.undoManager, "select y range[%f,%f]" % (ymin, ymax), mask, self.applyMask)
		action.do()
		self.checkUndoRedo()

	def onSelectLasso(self, vertices, axes):
		x, y = np.array(vertices).T
		x = np.ascontiguousarray(x, dtype=np.float64)
		y = np.ascontiguousarray(y, dtype=np.float64)
		#mask = np.zeros(len(self.dataset._length), dtype=np.uint8)
		mask = np.zeros(self.dataset._fraction_length, dtype=np.bool)
		meanx = x.mean()
		meany = y.mean()
		radius = np.sqrt((meanx-x)**2 + (meany-y)**2).max()
		#print (x, y, self.parent.datax, self.parent.datay, mask, meanx, meany, radius)
		#for (blockx, blocky), info in self.dataset.evaluate(*self.expressions[:2]):
		t0 = time.time()
		def select(info, blockx, blocky):
			self.message("selection at %.1f%% (%.2fs)" % (info.percentage, time.time() - t0), index=40)
			QtCore.QCoreApplication.instance().processEvents()
			#gavi.selection.pnpoly(x, y, blockx, blocky, mask[info.i1:info.i2], meanx, meany, radius)
			print "start pnpoly"
			print x, y, blockx, blocky, mask[info.i1:info.i2], meanx, meany, radius
			args = (x, y, blockx, blocky, mask[info.i1:info.i2])
			for arg in args:
				print arg.shape, arg.dtype

			if 1:
				submask = mask[info.i1:info.i2]
				#sub_counts = np.zeros((self.pool.nthreads, N, N), dtype=np.float64)
				def subblock(index, sub_i1, sub_i2):
					subspacefind.pnpoly(x, y, blockx[sub_i1:sub_i2], blocky[sub_i1:sub_i2], submask[sub_i1:sub_i2], meanx, meany, radius)
				self.pool.run_blocks(subblock, info.size)
			else:
				subspacefind.pnpoly(x, y, blockx, blocky, mask[info.i1:info.i2], meanx, meany, radius)
			print "now doing logical op"
			mask[info.i1:info.i2] = self.select_mode(None if self.dataset.mask is None else self.dataset.mask[info.i1:info.i2], mask[info.i1:info.i2])
			if info.last:
				self.message("selection %.2fs" % (time.time() - t0), index=40)

		self.dataset.evaluate(select, self.expressions[axes.xaxis_index], self.expressions[axes.yaxis_index], **self.getVariableDict())
		if 0:
			try:
				gavi.selection.pnpoly(x, y, self.getdatax(), self.getdatay(), mask, meanx, meany, radius)
			except:
				print gavi.selection.pnpoly.inspect_types()
				args = (x, y, self.getdatax(), self.getdatay(), mask, meanx, meany, radius)
				print "issue with pnppoly, arguments: "
				for i, arg in enumerate(args):
					print i, repr(arg), arg.dtype if hasattr(arg, "dtype") else ""
				raise
		action = undo.ActionMask(self.undoManager, "lasso around [%f,%f]" % (meanx, meany), mask, self.applyMask)
		action.do()
		self.checkUndoRedo()
		#self.dataset.selectMask(mask)
		#self.jobsManager.execute()
		#self.setMode(self.lastAction)


	def set_ranges(self, axis_indices, ranges=None, ranges_show=None, range_level=None):
		logger.debug("set axis/ranges/ranges_show: %r / %r / %r" % (axis_indices, ranges, ranges_show))
		if axis_indices is None: # signals a 'reset'
			for axis_index in range(self.dimensions):
				self.ranges_show[axis_index] = None
				self.ranges[axis_index] = None
		else:
			print axis_indices, self.ranges_show, ranges_show
			for i, axis_index in enumerate(axis_indices):
				if ranges_show:
					self.ranges_show[axis_index] = ranges_show[i]
				if ranges:
					self.ranges[axis_index] = ranges[i]
		logger.debug("set range_level: %r" % (range_level, ))
		self.range_level = range_level
		if len(axis_indices) > 0:
			self.check_aspect(axis_indices[0]) # maybe we should use the widest or smallest one

		self.update_plot()

	def update_plot(self):
		# default value
		self.update_direct()

	def update_direct(self):
		for i in range(self.dimensions):
			self.ranges[i] = self.ranges_show[i]
		timelog("begin computation", reset=True)
		self.compute()
		self.jobsManager.execute()
		timelog("computation done")

	def update_delayed(self, delay=500):
		def update(ignore=None, update_counter=None):
			print "COUNTER " * 100, self.update_counter, update_counter
			if self.update_counter > update_counter:
				pass  # ignore this event, a new one will arrive
				print "IGNORE " * 100
			else:
				self.update_direct()

		self.update_counter += 1
		QtCore.QTimer.singleShot(delay, functools.partial(update, update_counter=self.update_counter))

	def eval_amplitude(self, expression, locals):
		amplitude = None
		locals = dict(locals)
		if "gf" not in locals:
			locals["gf"] = scipy.ndimage.gaussian_filter
		counts = locals["counts"]
		if self.dimensions == 2:
			peak_columns = np.apply_along_axis(np.nanmax, 1, counts)
			peak_columns[peak_columns==0] = 1.
			peak_columns = peak_columns.reshape((1, -1))#.T
			locals["peak_columns"] = peak_columns


			sum_columns = np.apply_along_axis(np.nansum, 1, counts)
			sum_columns[sum_columns==0] = 1.
			sum_columns = sum_columns.reshape((1, -1))#.T
			locals["sum_columns"] = sum_columns

			peak_rows = np.apply_along_axis(np.nanmax, 0, counts)
			peak_rows[peak_rows==0] = 1.
			peak_rows = peak_rows.reshape((-1, 1))#.T
			locals["peak_rows"] = peak_rows

			sum_rows = np.apply_along_axis(np.nansum, 0, counts)
			sum_rows[sum_rows==0] = 1.
			sum_rows = sum_rows.reshape((-1, 1))#.T
			locals["sum_rows"] = sum_rows

		weighted = locals["weighted"]
		if weighted is None:
			locals["average"] = None
		else:
			average = weighted/counts
			average[counts==0] = np.nan
			locals["average"] = average
		globals = np.__dict__
		amplitude = eval(expression, globals, locals)
		return amplitude


	def zoom(self, factor, axes, x=None, y=None, delay=300, *args):
		xmin, xmax = axes.get_xlim()
		width = xmax - xmin

		if x is None:
			x = xmin + width/2

		fraction = (x-xmin)/width

		range_level = None
		ranges_show = []
		ranges = []
		axis_indices = []

		ranges_show.append((x - width *fraction *factor , x + width * (1-fraction)*factor))
		axis_indices.append(axes.xaxis_index)

		ymin, ymax = axes.get_ylim()
		height = ymax - ymin
		if y is None:
			y = ymin + height/2
		fraction = (y-ymin)/height
		ymin_show, ymax_show = y - height*fraction*factor, y + height*(1-fraction)*factor
		ymin_show, ymax_show = min(ymin_show, ymax_show), max(ymin_show, ymax_show)
		if len(self.ranges_show) == 1: # if 1d, y refers to range_level
			#range_level = ymin_show, ymax_show
			#range_level = ymin_show, ymax_show
			#counts_weights = np.array([1., factor]) if self.weight_expression is not None else None
			#w1, w2 = self.eval_amplitude(counts=np.array([1., factor]), counts_weights=counts_weights)
			#print ">" * 20, w1, w2
			#print counts_weights
			if (QtGui.QApplication.keyboardModifiers() == QtCore.Qt.AltModifier) or (QtGui.QApplication.keyboardModifiers() == QtCore.Qt.ControlModifier):
				range_level = ymin, ymax
				#a = b
			else:
				range_level = ymin_show, ymax_show
		else:
			ranges_show.append((ymin_show, ymax_show))
			axis_indices.append(axes.yaxis_index)


		#self.update = self.update_delayed


		def delayed_zoom():
			#action = undo.ActionZoom(self.undoManager, "zoom " + ("out" if factor > 1 else "in"), self.set_ranges,
			#				range(self.dimensions), self.ranges, self.ranges_show,
			#				self.range_level, axis_indices, ranges_show=ranges_show, range_level=range_level)
			action = undo.ActionZoom(self.undoManager, "zoom " + ("out" if factor > 1 else "in"), self.set_ranges,
							range(self.dimensions), self.ranges, self.ranges,
							self.range_level, axis_indices, ranges_show=ranges_show, range_level=range_level)
			action.do()
			self.checkUndoRedo()
		self.queue_update(delayed_zoom, delay=delay)


		if 1:
			if self.dimensions == 2:
				self.ranges_show[axis_indices[0]] = list(ranges_show[0])
				self.ranges_show[axis_indices[1]] = list(ranges_show[1])
				axes.set_xlim(self.ranges_show[0])
				axes.set_ylim(self.ranges_show[1])
			if self.dimensions == 1:
				self.ranges_show[axis_indices[0]] = list(ranges_show[0])
				self.range_level = list(range_level)
				axes.set_xlim(self.ranges_show[0])
				axes.set_ylim(self.range_level)
			self.queue_redraw()
			#self.plot()

		if 0: #recalculate:
			def update(ignore=None, update_counter=None):
				if self.update_counter > update_counter:
					pass  # ignore this event, a new one will arrive
					print "IGNORE " * 10
				else:
					for axisIndex in range(self.dimensions):
						linkButton = self.linkButtons[axisIndex]
						link = linkButton.link
						if link:
							logger.debug("sending link messages")
							link.sendRangesShow(self.ranges_show[axisIndex], linkButton)
							#link.sendPlot(linkButton)


					linked_buttons = [button for button in self.linkButtons if button.link is not None]
					links = [button.link for button in linked_buttons]
					if len(linked_buttons) > 0:
						logger.debug("sending compute message")
						gavi.dataset.Link.sendCompute(links, linked_buttons)
					#self.compute()
					logger.debug("now execute")
					self.jobsManager.execute()
					logger.debug("execute finished")

			self.update_counter += 1
			QtCore.QTimer.singleShot(1000, functools.partial(update, update_counter=self.update_counter))


	def autoRecalculate(self):
		return True


	def onActionSaveFigure(self, *ignore_args):
		filetypes = dict(self.fig.canvas.get_supported_filetypes()) # copy, otherwise we lose png support :)
		pngtype = [("png", filetypes["png"])]
		del filetypes["png"]
		filetypes = [value + "(*.%s)" % key for (key, value) in pngtype + filetypes.items()]
		import string
		def make_save(expr):
			save_expr = ""
			for char in expr:
				if char not in string.whitespace:
					if char in string.ascii_letters or char in string.digits or char in "._":
						save_expr += char
					else:
						save_expr += "_"
			return save_expr
		save_expressions = map(make_save, self.expressions)
		type = "histogram" if self.dimensions == 1 else "density"
		filename = self.dataset.name +"_%s_" % type  +"-vs-".join(save_expressions) + ".png"
		filename = QtGui.QFileDialog.getSaveFileName(self, "Export to figure", filename, ";;".join(filetypes))
		if isinstance(filename, tuple):
			filename = filename[0]
		filename = str(filename)
		if filename:
			logger.debug("saving to figure: %s" % filename)
			self.fig.savefig(filename)
			self.filename_figure_last = filename
			self.action_save_figure_again.setEnabled(True)

	def onActionSaveFigureAgain(self, *ignore_args):
		logger.debug("saving to figure: %s" % self.filename_figure_last)
		self.fig.savefig(self.filename_figure_last)


	def get_aspect(self):
		if 0:
			xmin, xmax = self.axes.get_xlim()
			ymin, ymax = self.axes.get_ylim()
			height = ymax - ymin
			width = xmax - xmin
		return 1 #width/height

	def onActionAspectLockOne(self, *ignore_args):
		self.aspect = self.get_aspect() if self.action_aspect_lock_one.isChecked() else None
		logger.debug("set aspect to: %r" % self.aspect)
		self.check_aspect(0)
		self.compute()
		self.jobsManager.execute()
		#self.plot()

	def _onActionAspectLockOne(self, *ignore_args):
		self.aspect = 1 #self.get_aspect() if self.action_aspect_lock.isEnabled() else None
		logger.debug("set aspect to: %r" % self.aspect)


	def time_step(self):
		print "time", self.getVariableDict()
		self.update_plot()
		playing = self.action_play_stop.isChecked()
		if playing and self.isVisible():
			QtCore.QTimer.singleShot(10, self.time_step)


	def on_play_stop(self, ignore=None):
		#self.action_play_stop.toggle()
		play = self.action_play_stop.isChecked()
		print "time", self.getVariableDict(), play
		if play:
			self.t_0 = time.time()
			self.time_step()



	def addToolbar2(self, layout, contrast=True, gamma=True):
		self.toolbar2 = QtGui.QToolBar(self)
		self.toolbar2.setToolButtonStyle(QtCore.Qt.ToolButtonTextUnderIcon)
		self.toolbar2.setIconSize(QtCore.QSize(16, 16))

		layout.addWidget(self.toolbar2)


		self.action_play_stop = QtGui.QAction(QtGui.QIcon(iconfile('table_save')), '&Play', self)
		self.action_play_stop.setCheckable(True)

		#self.toolbar2.addAction(self.action_play_stop)

		self.action_play_stop.triggered.connect(self.on_play_stop)

		self.action_save_figure = QtGui.QAction(QtGui.QIcon(iconfile('table_save')), '&Export figure', self)
		self.action_save_figure_again = QtGui.QAction(QtGui.QIcon(iconfile('table_save')), '&Export figure again', self)
		self.menu_save = QtGui.QMenu(self)
		self.action_save_figure.setMenu(self.menu_save)
		self.menu_save.addAction(self.action_save_figure_again)
		self.toolbar2.addAction(self.action_save_figure)

		self.action_save_figure.triggered.connect(self.onActionSaveFigure)
		self.action_save_figure_again.triggered.connect(self.onActionSaveFigureAgain)
		self.action_save_figure_again.setEnabled(False)


		self.action_aspect_lock_one = QtGui.QAction(QtGui.QIcon(iconfile('control-stop-square')), 'Aspect=1', self)
		#self.action_aspect_lock_one = QtGui.QAction(QtGui.QIcon(iconfile('table_save')), '&Set aspect to one', self)
		#self.menu_aspect = QtGui.QMenu(self)
		#self.action_aspect_lock.setMenu(self.menu_aspect)
		#self.menu_aspect.addAction(self.action_aspect_lock_one)
		self.toolbar2.addAction(self.action_aspect_lock_one)

		#self.action_aspect_lock.triggered.connect(self.onActionAspectLock)
		self.action_aspect_lock_one.setCheckable(True)
		self.action_aspect_lock_one.triggered.connect(self.onActionAspectLockOne)
		#self.action_save_figure_again.setEnabled(False)






		self.action_undo = QtGui.QAction(QtGui.QIcon(iconfile('arrow-curve-180-left')), 'Undo', self)
		self.action_redo = QtGui.QAction(QtGui.QIcon(iconfile('arrow-curve-000-left')), 'Redo', self)

		self.toolbar2.addAction(self.action_undo)
		self.toolbar2.addAction(self.action_redo)
		self.action_undo.triggered.connect(self.onActionUndo)
		self.action_redo.triggered.connect(self.onActionRedo)

		self.action_shuffled = QtGui.QAction(QtGui.QIcon(iconfile('table-select-cells')), 'Shuffled', self)
		self.action_shuffled.setCheckable(True)
		self.action_shuffled.triggered.connect(self.onActionShuffled)
		self.toolbar2.addAction(self.action_shuffled)

		self.action_disjoin = QtGui.QAction(QtGui.QIcon(iconfile('sql-join-outer-exclude')), 'Disjoined', self)
		self.action_disjoin.setCheckable(True)
		self.action_disjoin.triggered.connect(self.onActionDisjoin)
		self.toolbar2.addAction(self.action_disjoin)


		self.action_axes_lock = QtGui.QAction(QtGui.QIcon(iconfile('lock')), 'Lock axis', self)
		self.action_axes_lock.setCheckable(True)
		self.action_axes_lock.triggered.connect(self.onActionAxesLock)
		self.toolbar2.addAction(self.action_axes_lock)

	def onActionAxesLock(self, ignore=None):
		self.axis_lock = self.action_axes_lock.isChecked()

	def onActionShuffled(self, ignore=None):
		self.xoffset = 1 if self.action_shuffled.isChecked() else 0
		self.compute()
		self.jobsManager.execute()
		logger.debug("xoffset = %r" % self.xoffset)

	def onActionDisjoin(self, ignore=None):
		#self.xoffset = 1 if self.action_shuffled.isChecked() else 0
		self.show_disjoined = self.action_disjoin.isChecked()
		self.compute()
		self.jobsManager.execute()
		logger.debug("show_disjoined = %r" % self.show_disjoined)

	def onActionImageInvert(self, ignore=None):
		self.image_invert = self.button_image_invert.isChecked()
		self.plot()

	def update_gamma_label(self):
		text = "gamma=%.3f" % self.image_gamma
		self.label_gamma.setText(text)

	def onGammaChange(self, gamma_index):
		self.image_gamma = 10**(gamma_index / 100./2)
		print "Gamma", self.image_gamma
		self.update_gamma_label()
		self.queue_replot()

	def normalize(self, array):
		#return (array - np.nanmin(array)) / (np.nanmax(array) - np.nanmin(array))
		return array

	def image_post(self, array):
		return -array if self.image_invert else array

	def contrast_none(self, array):
		return self.image_post(self.normalize(array)**(self.image_gamma))

	def contrast_none_auto(self, array, percentage=1.):
		values = array.reshape(-1)
		mask = np.isinf(values)
		values = values[~mask]
		indices = np.argsort(values)
		min, max = np.nanmin(values), np.nanmax(values)
		N = len(values)
		i1, i2 = int(N * percentage / 100), int(N-N * percentage / 100)
		v1, v2 = values[indices[i1]], values[indices[i2]]
		print "contrast[%f%%]" % percentage, "from[%f-%f] to [%f-%f]" % (min, max, v1, v2)
		print i1, i2, N
		return self.image_post(self.normalize(np.clip(array, v1, v2))**self.image_gamma)

	def onActionContrast(self):
		index = self.contrast_list.index(self.contrast)
		next_index = (index + 1) % len(self.contrast_list)
		self.contrast = self.contrast_list[next_index]
		print self.contrast
		self.plot()


	def addToolbar(self, layout, pick=True, xselect=True, yselect=True, lasso=True):

		self.toolbar = QtGui.QToolBar(self)
		self.toolbar.setToolButtonStyle(QtCore.Qt.ToolButtonTextUnderIcon)
		self.action_group_main = QtGui.QActionGroup(self)
		self.action_group_mainSelectMode = QtGui.QActionGroup(self)


		self.action_group_display = QtGui.QActionGroup(self)

		self.actiongroup_mini_mode = QtGui.QActionGroup(self)
		self.action_mini_mode = QtGui.QAction(QtGui.QIcon(iconfile('picture_empty')), '&Mini screen(should not see)', self)
		self.action_mini_mode_normal = QtGui.QAction(QtGui.QIcon(iconfile('picture_empty')), '&compact', self)
		self.action_mini_mode_ultra  = QtGui.QAction(QtGui.QIcon(iconfile('picture_empty')), '&compact+', self)

		self.action_fullscreen = QtGui.QAction(QtGui.QIcon(iconfile('picture_empty')), '&fullscreen', self)
		self.action_fullscreen.setCheckable(True)

		self.action_toolbar_toggle = QtGui.QAction(QtGui.QIcon(iconfile('picture_empty')), '&toolbars', self)
		self.action_toolbar_toggle.setCheckable(True)
		self.action_toolbar_toggle.setChecked(True)

		self.actiongroup_mini_mode.addAction(self.action_mini_mode_normal)
		self.actiongroup_mini_mode.addAction(self.action_mini_mode_ultra)
		#self.actiongroup_mini_mode.addAction(self.action_fullscreen)


		def toggle_fullscreen(ignore=None):
			fullscreen = self.windowState() & QtCore.Qt.WindowFullScreen
			fullscreen = not fullscreen # toggle
			self.action_fullscreen.setChecked(fullscreen)
			print "fullscreen", fullscreen
			if fullscreen:
				self.setWindowState(self.windowState() | QtCore.Qt.WindowFullScreen);
			else:
				self.setWindowState(self.windowState() ^ QtCore.Qt.WindowFullScreen);

		self.action_fullscreen.triggered.connect(toggle_fullscreen)


		self.action_toolbar_toggle.triggered.connect(self.on_toolbar_toggle)

		self.action_move = QtGui.QAction(QtGui.QIcon(iconfile('edit-move')), '&Move', self)
		self.action_pick = QtGui.QAction(QtGui.QIcon(iconfile('cursor')), '&Pick', self)

		self.action_select = QtGui.QAction(QtGui.QIcon(iconfile('glue_lasso16')), '&Select(you should not read this)', self)
		self.action_xrange = QtGui.QAction(QtGui.QIcon(iconfile('glue_xrange_select16')), '&x-range', self)
		self.action_yrange = QtGui.QAction(QtGui.QIcon(iconfile('glue_yrange_select16')), '&y-range', self)
		self.action_lasso = QtGui.QAction(QtGui.QIcon(iconfile('glue_lasso16')), '&Lasso', self)
		self.action_select_none = QtGui.QAction(QtGui.QIcon(iconfile('dialog-cancel-3')), '&No selection', self)
		self.action_select_invert = QtGui.QAction(QtGui.QIcon(iconfile('dialog-cancel-3')), '&Invert', self)

		self.action_select_mode_replace = QtGui.QAction(QtGui.QIcon(iconfile('sql-join-right')), '&Replace', self)
		self.action_select_mode_and = QtGui.QAction(QtGui.QIcon(iconfile('sql-join-inner')), '&And', self)
		self.action_select_mode_or = QtGui.QAction(QtGui.QIcon(iconfile('sql-join-outer')), '&Or', self)
		self.action_select_mode_xor = QtGui.QAction(QtGui.QIcon(iconfile('sql-join-outer-exclude')), 'Xor', self)
		self.action_select_mode_subtract = QtGui.QAction(QtGui.QIcon(iconfile('sql-join-left-exclude')), 'Subtract', self)


		self.action_samp_sand_table_select_row_list = QtGui.QAction(QtGui.QIcon(iconfile('block--arrow')), 'sel->SAMP', self)
		self.action_samp_sand_table_select_row_list.setShortcut('S')
		self.toolbar.addAction(self.action_samp_sand_table_select_row_list)
		def send_samp_selection(ignore=None):
			self.signal_samp_send_selection.emit(self.dataset)
		self.send_samp_selection_reference = send_samp_selection # does this fix the bug that clicking the buttons doesn't do anything?
		self.action_samp_sand_table_select_row_list.triggered.connect(send_samp_selection)

		self.action_display_mode_both = QtGui.QAction(QtGui.QIcon(iconfile('picture_empty')), 'Show both', self)
		self.action_display_mode_full = QtGui.QAction(QtGui.QIcon(iconfile('picture_empty')), 'Show full', self)
		self.action_display_mode_selection = QtGui.QAction(QtGui.QIcon(iconfile('picture_empty')), 'Show selection', self)
		self.action_display_mode_both_contour = QtGui.QAction(QtGui.QIcon(iconfile('picture_empty')), 'Show contour', self)


		self.action_res_1 = QtGui.QAction(QtGui.QIcon(iconfile('picture_empty')), 'res 1', self)
		self.action_res_2 = QtGui.QAction(QtGui.QIcon(iconfile('picture_empty')), 'res 2', self)
		self.action_res_3 = QtGui.QAction(QtGui.QIcon(iconfile('picture_empty')), 'res 3', self)
		self.action_res_4 = QtGui.QAction(QtGui.QIcon(iconfile('picture_empty')), 'res 4', self)
		self.action_res_5 = QtGui.QAction(QtGui.QIcon(iconfile('picture_empty')), 'res 5', self)

		for res, action in zip([128, 256, 512, 1024, 2048], [self.action_res_1, self.action_res_2, self.action_res_3, self.action_res_4, self.action_res_5]):
			def do(ignore=None, res=res):
				self.grid_size = res
				self.compute()
				self.jobsManager.execute()
			action.triggered.connect(do)


		self.actions_display = [self.action_display_mode_both, self.action_display_mode_full, self.action_display_mode_selection, self.action_display_mode_both_contour]
		for action in self.actions_display:
			self.action_group_display.addAction(action)
			action.setCheckable(True)
		action = self.actions_display[0]
		action.setChecked(True)
		self.action_display_current = action
		self.action_group_display.triggered.connect(self.onActionDisplay)
		#self.zoomButton = QtGui.QToolButton(self, )
		#$self.zoomButton.setIcon(QtGui.QIcon(iconfile('glue_zoom_to_rect')))
		#self.zoomMenu = QtGui.QMenu(self)
		#self.zoomMenu.addAction(self.action_zoom_x)
		#self.zoomMenu.addAction(self.action_zoom_y)
		#self.zoomMenu.addAction(self.action_zoom_out)
		#self.action_zoom.setMenu(self.zoomMenu)
		#self.action_zoom = self.toolbar.addWidget(self.zoomButton)

		#self.action_zoom = QtGui.QAction(QtGui.QIcon(iconfile('glue_zoom_to_rect')), '&Zoom', self)
		#exitAction.setShortcut('Ctrl+Q')
		#onExAction.setStatusTip('Exit application')

		#self.action_group_main.setToggleAction(True)
		#self.action_group_main.setExclusive(True)
		self.action_group_mainSelectMode.addAction(self.action_select_mode_replace)
		self.action_group_mainSelectMode.addAction(self.action_select_mode_and)
		self.action_group_mainSelectMode.addAction(self.action_select_mode_or)
		self.action_group_mainSelectMode.addAction(self.action_select_mode_xor)
		self.action_group_mainSelectMode.addAction(self.action_select_mode_subtract)

		self.action_group_main.addAction(self.action_move)
		self.action_group_main.addAction(self.action_pick)
		self.action_group_main.addAction(self.action_xrange)
		self.action_group_main.addAction(self.action_yrange)
		self.action_group_main.addAction(self.action_lasso)
		#self.action_group_main.addAction(self.action_zoom_out)



		#self.mini_mode_button = QtGui.QToolButton()
		#self.mini_mode_button.setPopupMode(QtGui.QToolButton.InstantPopup)
		#self.mini_mode_button.setToolButtonStyle(QtCore.Qt.ToolButtonTextUnderIcon)
		self.menu_mini_mode = QtGui.QMenu()
		self.action_mini_mode.setMenu(self.menu_mini_mode)
		#self.mini_mode_button.setMenu(self.mini_mode_button_menu)
		self.menu_mini_mode.addAction(self.action_mini_mode_normal)
		self.menu_mini_mode.addAction(self.action_mini_mode_ultra)
		#self.mini_mode_button.setDefaultAction(self.action_miniscreen)
		#self.mini_mode_button.setCheckable(True)
		#self.mini_mode_button.setIcon(self.action_miniscreen.icon())
		#self.mini_mode_button.setText(self.action_miniscreen.text())

		self.toolbar.addAction(self.action_mini_mode)
		self.toolbar.addAction(self.action_fullscreen)
		self.toolbar.addAction(self.action_toolbar_toggle)

		self.toolbar.addAction(self.action_move)
		if pick:
			self.toolbar.addAction(self.action_pick)
			#self.action_pick.setChecked(True)
			#self.setMode(self.action_pick, force=True)
			self.lastAction = self.action_pick
		self.toolbar.addAction(self.action_select)
		self.select_menu = QtGui.QMenu()
		self.action_select.setMenu(self.select_menu)
		self.select_menu.addAction(self.action_lasso)
		if yselect:
			#self.toolbar.addAction(self.action_yrange)
			self.select_menu.addAction(self.action_yrange)
			if self.dimensions > 1:
				self.lastActionSelect = self.action_yrange
		if xselect:
			#self.toolbar.addAction(self.action_xrange)
			self.select_menu.addAction(self.action_xrange)
			self.lastActionSelect = self.action_xrange
		if lasso:
			#self.toolbar.addAction(self.action_lasso)
			if self.dimensions > 1:
				self.lastActionSelect = self.action_lasso
		else:
			self.action_lasso.setEnabled(False)
		self.select_menu.addSeparator()
		self.select_menu.addAction(self.action_select_none)
		self.select_menu.addAction(self.action_select_invert)
		self.select_menu.addSeparator()


		self.select_mode_button = QtGui.QToolButton()
		self.select_mode_button.setPopupMode(QtGui.QToolButton.InstantPopup)
		self.select_mode_button.setToolButtonStyle(QtCore.Qt.ToolButtonTextUnderIcon)
		self.select_mode_button_menu = QtGui.QMenu()
		self.select_mode_button.setMenu(self.select_mode_button_menu)

		self.select_mode_button_menu.addAction(self.action_select_mode_replace)
		self.select_mode_button_menu.addAction(self.action_select_mode_or)
		self.select_mode_button_menu.addAction(self.action_select_mode_and)
		self.select_mode_button_menu.addAction(self.action_select_mode_xor)
		self.select_mode_button_menu.addAction(self.action_select_mode_subtract)
		self.select_mode_button.setDefaultAction(self.action_select_mode_replace)
		self.toolbar.addWidget(self.select_mode_button)


		#self.toolbar.addAction(action_select_mode)
		if 0:
			self.toolbar.addAction(self.action_zoom)
			self.zoom_menu = QtGui.QMenu()
			self.action_zoom.setMenu(self.zoom_menu)
			self.zoom_menu.addAction(self.action_zoom_rect)
			self.zoom_menu.addAction(self.action_zoom_x)
			self.zoom_menu.addAction(self.action_zoom_y)
			if self.dimensions == 1:
				self.lastActionZoom = self.action_zoom_x # this makes more sense for histograms as default
			else:
				self.lastActionZoom = self.action_zoom_rect

			self.toolbar.addSeparator()
			self.toolbar.addAction(self.action_zoom_out)
			self.toolbar.addAction(self.action_zoom_fit)
			#self.toolbar.addAction(self.action_zoom_use)
		else:
			#self.plugin_zoom.plug()
			#
			plugin_chain_toolbar = sorted(self.plugin_queue_toolbar, key=itemgetter(1)) # sort by order field
			for plug, order in plugin_chain_toolbar:
				plug()

		#self.zoomButton.setPopupMode(QtCore.QToolButton.DelayedPopup)


		self.action_group_main.triggered.connect(self.setMode)
		self.action_group_mainSelectMode.triggered.connect(self.setSelectMode)

		self.action_mini_mode.triggered.connect(self.onActionMiniMode)
		self.action_mini_mode_normal.triggered.connect(self.onActionMiniModeNormal)
		self.action_mini_mode_ultra.triggered.connect(self.onActionMiniModeUltra)
		self.action_select.triggered.connect(self.onActionSelect)
		self.action_select_none.triggered.connect(self.onActionSelectNone)
		self.action_select_invert.triggered.connect(self.onActionSelectInvert)
		#action_zoom_out

		self.action_select_mode_replace.setCheckable(True)
		self.action_select_mode_and.setCheckable(True)
		self.action_select_mode_or.setCheckable(True)
		self.action_select_mode_xor.setCheckable(True)
		self.action_select_mode_subtract.setCheckable(True)

		self.action_mini_mode.setCheckable(True)
		self.action_mini_mode_normal.setCheckable(True)
		self.action_mini_mode_ultra.setCheckable(True)
		self.action_mini_mode_ultra.setChecked(True)
		self.action_mini_mode.setIcon(self.action_mini_mode_ultra.icon())
		self.action_mini_mode.setText(self.action_mini_mode_ultra.text())

		self.action_move.setCheckable(True)
		self.action_pick.setCheckable(True)
		self.action_move.setChecked(True)
		self.action_select.setCheckable(True)
		self.action_xrange.setCheckable(True)
		self.action_yrange.setCheckable(True)
		self.action_lasso.setCheckable(True)
		#self.action_zoom_out.setCheckable(True)
		#self.action_group_main.

		#action = self.toolbar.addAction(icon
		self.syncToolbar()
		#self.action_select_mode_replace.setChecked(True)
		self.select_mode = self.select_replace
		self.setMode(self.action_move)
		self.toolbar.setIconSize(QtCore.QSize(16, 16))
		layout.addWidget(self.toolbar)

	def onActionDisplay(self, action):
		print "display:", action.text()
		self.action_display_current = action
		self.plot()

	def onActionMiniMode(self):
		#targetAction = self.mini_mode_button.defaultAction()
		enabled_mini_mode = self.action_mini_mode.isChecked()
		#enabled_mini_mode = self.action_mini_mode_normal.isChecked() or self.action_mini_mode_ultra.isChecked()
		ultra_mode = self.action_mini_mode_ultra.isChecked()

		logger.debug("mini screen: %r (ultra: %r)" % (enabled_mini_mode, ultra_mode))
		toolbuttons = self.toolbar.findChildren(QtGui.QToolButton)
		for toolbutton in toolbuttons:
			#print toolbutton
			toolbutton.setToolButtonStyle(QtCore.Qt.ToolButtonIconOnly if enabled_mini_mode else QtCore.Qt.ToolButtonTextUnderIcon)

		if enabled_mini_mode:
			values = self.fig.subplotpars
			self.subplotpars_values = {"left":values.left, "right":values.right, "bottom":values.bottom, "top":values.top}
			print self.subplotpars_values
			self.bottomHeight = self.bottomFrame.height()

		self.bottomFrame.setVisible(not enabled_mini_mode)
		if 0:
			if enabled_mini_mode:
				self.resize(QtCore.QSize(self.width(), self.height() - self.bottomHeight))
			else:
				self.resize(QtCore.QSize(self.width(), self.height() + self.bottomHeight))
		if enabled_mini_mode:
			if ultra_mode:
				self.fig.subplots_adjust(left=0, right=1, bottom=0, top=1.)
				self.canvas.draw()
		else:
			self.fig.subplots_adjust(**self.subplotpars_values)
			self.canvas.draw()

	def on_toolbar_toggle(self, ignore=None):
		self.action_toolbar_toggle.toggle()
		visible = self.action_toolbar_toggle.isChecked()
		print "toolbar visible", visible
		for widget in [self.toolbar, self.toolbar2, self.status_bar]:
			widget.setVisible(visible)

	def onActionMiniModeNormal(self, *args):
		#self.mini_mode_button.setDefaultAction(self.action_miniscreen)
		#self.action_miniscreen.setChecked(True)
		#self.action_miniscreen_ultra.setChecked(False)
		#self.on
		#logger.debug("normal mini screen: %r" % self.action_miniscreen.isChecked())
		self.action_mini_mode.setIcon(self.action_mini_mode_normal.icon())
		self.action_mini_mode.setText(self.action_mini_mode_normal.text())
		#self.onActionMiniMode()
		self.action_mini_mode.trigger()
		pass

	def onActionMiniModeUltra(self, *args):
		#self.mini_mode_button.setDefaultAction(self.action_miniscreen_ultra)
		#logger.debug("ultra mini screen: %r" % self.action_miniscreen_ultra.isChecked())
		self.action_mini_mode.setIcon(self.action_mini_mode_ultra.icon())
		self.action_mini_mode.setText(self.action_mini_mode_ultra.text())
		self.action_mini_mode.trigger()
		#self.onActionMiniMode()
		#self.onActionMiniScreen()
		#self.action_miniscreen.setChecked(False)
		#self.action_miniscreen_ultra.setChecked(True)

	def setSelectMode(self, action):
		self.select_mode_button.setDefaultAction(action)
		if action == self.action_select_mode_replace:
			self.select_mode = self.select_replace
		if action == self.action_select_mode_and:
			self.select_mode = self.select_and
		if action == self.action_select_mode_or:
			self.select_mode = self.select_or
		if action == self.action_select_mode_xor:
			self.select_mode = self.select_xor
		if action == self.action_select_mode_subtract:
			self.select_mode = self.select_subtract

	def select_replace(self, maskold, masknew):
		return masknew

	def select_and(self, maskold, masknew):
		return masknew if maskold is None else maskold & masknew

	def select_or(self, maskold, masknew):
		return masknew if maskold is None else maskold | masknew

	def select_xor(self, maskold, masknew):
		return masknew if maskold is None else maskold ^ masknew

	def select_subtract(self, maskold, masknew):
		return masknew if maskold is None else (maskold) & ~masknew

	def onActionSelectNone(self):
		#self.dataset.selectMask(None)
		#self.jobsManager.execute()
		action = undo.ActionMask(self.undoManager, "clear selection", None, self.applyMask)
		action.do()
		self.checkUndoRedo()

	def onActionSelectInvert(self):
		mask = self.dataset.mask
		if mask is not None:
			mask = ~mask
		else:
			mask = np.ones(len(self.dataset), dtype=np.bool)
		action = undo.ActionMask(self.undoManager, "invert selection", mask, self.applyMask)
		action.do()
		self.checkUndoRedo()

	def onActionSelect(self):
		self.lastActionSelect.setChecked(True)
		self.setMode(self.lastActionSelect)
		self.syncToolbar()

	def syncToolbar(self):
		for plugin in self.plugins:
			plugin.syncToolbar()
		for action in [self.action_select]: #, self.action_zoom]:
			logger.debug("sync action: %r" % action.text())
			subactions = action.menu().actions()
			subaction_selected = [subaction for subaction in subactions if subaction.isChecked()]
			#if len(subaction_selected) > 0:
			#	action.setText(subaction_selected[0].text())
			#	action.setIcon(subaction_selected[0].icon())
			logger.debug(" subaction_selected: %r" % subaction_selected)
			logger.debug(" action was selected?: %r" % action.isChecked())
			action.setChecked(len(subaction_selected) > 0)
			logger.debug(" action  is selected?: %r" % action.isChecked())
		logger.debug("last select action: %r" % self.lastActionSelect.text())
		#logger.debug("last zoom action: %r" % self.lastActionZoom.text())
		self.action_select.setText(self.lastActionSelect.text())
		self.action_select.setIcon(self.lastActionSelect.icon())
		#self.action_zoom.setText(self.lastActionZoom.text())
		#self.action_zoom.setIcon(self.lastActionZoom.icon())
		#self.action_select.update()

	def check_aspect(self, axis_follow):
		if self.aspect is not None:
			otheraxes = range(self.dimensions)
			allaxes = range(self.dimensions)
			otheraxes.remove(axis_follow)
			print self.ranges_show, self.ranges, axis_follow
			ranges = [self.ranges_show[i] if self.ranges_show[i] is not None else self.ranges[i] for i in otheraxes]

			if None in ranges:
				return
			print ranges
			width = self.ranges_show[axis_follow][1] - self.ranges_show[axis_follow][0]
			#width = ranges[axis_follow][1] - ranges[axis_follow][0]
			center = (self.ranges[axis_follow][1] + self.ranges[axis_follow][0])/2.

			widths = [ranges[i][1] - ranges[i][0] for i in range(self.dimensions-1)]
			center = [(ranges[i][1] + ranges[i][0])/2. for i in range(self.dimensions-1)]


			#xmin, xmax = self.ranges[0]
			#ymin, ymax = self.ranges[1]
			for i in range(self.dimensions-1):
				axis_index = otheraxes[i]
				#if self.ranges_show[i] is None:
				#	self.ranges_show[i] = self.ranges[i]
				self.ranges_show[axis_index] = [None, None]
				self.ranges_show[axis_index][0] = center[i] - width/2
				self.ranges_show[axis_index][1] = center[i] + width/2
			for i in range(self.dimensions-1):
				axis_index = otheraxes[i]
				self.ranges[axis_index] = list(self.ranges_show[axis_index])

	def create_grid_map(self, gridsize, use_selection):
		locals = {}
		for name in self.grids.grids.keys():
			grid = self.grids.grids[name]
			if name == "counts" or (grid.weight_expression is not None and len(grid.weight_expression) > 0):
				if grid.max_size >= gridsize:
					locals[name] = grid.get_data(gridsize, use_selection=use_selection)
			else:
				locals[name] = None
		for d, name in zip(range(self.dimensions), "xyzw"):
			width = self.ranges[d][1] - self.ranges[d][0]
			offset = self.ranges[d][0]
			x = (np.arange(0, gridsize)+0.5)/float(gridsize) * width + offset
			locals[name] = x
		return locals




class HistogramPlotDialog(PlotDialog):
	names = "histogram,1d"
	def __init__(self, parent, jobsManager, dataset, expression, **kwargs):
		super(HistogramPlotDialog, self).__init__(parent, jobsManager, dataset, [expression], ["X"], **kwargs)

	def beforeCanvas(self, layout):
		self.addToolbar(layout, yselect=False, lasso=False)

	def _afterCanvas(self, layout):
		self.addToolbar2(layout, contrast=False, gamma=False)
		super(HistogramPlotDialog, self).afterCanvas(layout)

	def calculate_visuals(self, info, block, weights_block, weights_x_block, weights_y_block, weights_xy_block, compute_counter=None):
		if compute_counter < self.compute_counter:
			print "STOP " * 100
			return True
		if info.error:
			print "error", info.error_text
			self.expression_error = True
			self.message(info.error_text, index=-2)
			return
		elapsed = time.time() - info.time_start
		self.message("computation at %.1f%% (%.2fs)" % (info.percentage, elapsed), index=20)
		QtCore.QCoreApplication.instance().processEvents()

		self.expression_error = False
		N = self.grid_size
		mask = self.dataset.mask
		if info.first:
			self.selected_point = None
			self.counts = np.zeros(N, dtype=np.float64)
			if weights_block is not None:
				self.counts_weights = np.zeros(N, dtype=np.float64)
			else:
				self.counts_weights = None

			if mask is not None:
				self.counts_mask = np.zeros(N, dtype=np.float64) #mab.utils.numpy.mmapzeros((128), dtype=np.float64)
				self.counts_weights_mask = None
				if weights_block is not None:
					self.counts_weights_mask = np.zeros(N, dtype=np.float64)
			else:
				self.counts_mask = None
				self.counts_weights_mask = None

		#return
		xmin, xmax = self.ranges[0]
		if self.ranges_show[0] is None:
			self.ranges_show[0] = xmin, xmax
		#totalxmin, totalxmax = self.gettotalxrange()
		#print repr(self.data), repr(self.counts), repr(xmin), repr(xmax)
		t0 = time.time()
		try:
			args = (block, self.counts, xmin, xmax)
			#gavi.histogram.hist1d(block, self.counts, xmin, xmax)
			if 1:

				sub_counts = np.zeros((self.pool.nthreads, N), dtype=np.float64)
				def subblock(index, sub_i1, sub_i2):
					subspacefind.histogram1d(block[sub_i1:sub_i2], None, sub_counts[index], xmin, xmax)
				self.pool.run_blocks(subblock, info.size)
				self.counts += np.sum(sub_counts, axis=0)
			else:
				subspacefind.histogram1d(block, None, self.counts, xmin, xmax)

			if weights_block is not None:
				args = (block, self.counts, xmin, xmax, weights_block)
				#gavi.histogram.hist1d_weights(block, self.counts_weights, weights_block, xmin, xmax)
				#subspacefind.histogram1d(block, weights_block, self.counts_weights, xmin, xmax)
				sub_counts = np.zeros((self.pool.nthreads, N), dtype=np.float64)
				def subblock(index, sub_i1, sub_i2):
					subspacefind.histogram1d(block[sub_i1:sub_i2], weights_block[sub_i1:sub_i2], sub_counts[index], xmin, xmax)
				self.pool.run_blocks(subblock, info.size)
				self.counts_weights += np.sum(sub_counts, axis=0)

		except:
			logger.exception("error with hist1d, arguments: %r" % (args,))
		if mask is not None:
			subset = block[mask[info.i1:info.i2]]
			#gavi.histogram.hist1d(subset, self.counts_mask, xmin, xmax)
			sub_counts = np.zeros((self.pool.nthreads, N), dtype=np.float64)
			def subblock(index, sub_i1, sub_i2):
				subspacefind.histogram1d(subset[sub_i1:sub_i2], None, sub_counts[index], xmin, xmax)
			self.pool.run_blocks(subblock, len(subset))
			self.counts_mask += np.sum(sub_counts, axis=0)

			if weights_block is not None:
				subset_weights = weights_block[mask[info.i1:info.i2]]
				#gavi.histogram.hist1d_weights(subset, self.counts_weights_mask, subset_weights, xmin, xmax)
				sub_counts = np.zeros((self.pool.nthreads, N), dtype=np.float64)
				def subblock(index, sub_i1, sub_i2):
					subspacefind.histogram1d(subset[sub_i1:sub_i2], subset_weights[sub_i1:sub_i2], sub_counts[index], xmin, xmax)
				self.pool.run_blocks(subblock, len(subset))
				self.counts_mask += np.sum(sub_counts, axis=0)

		print "it took", time.time()-t0

		index = self.dataset.selected_row_index
		if index is not None:
			if index >= info.i1 and index < info.i2: # selected point is in this block
				self.selected_point = block[index-info.i1]

		self.delta = (xmax - xmin) / N
		self.centers = np.arange(N) * self.delta + xmin
		#print xmin, xmax, self.centers
		if info.last:
			elapsed = time.time() - info.time_start
			self.message("computation %.2f s" % (elapsed), index=20)
			self.message(None, index=-2) # clear error


	def plot(self):
		t0 = time.time()
		self.axes.cla()
		self.axes.autoscale(False)
		#if self.expression_error:
		#	return
		#P.hist(x, 50, normed=1, histtype='stepfilled')
		#values =
		Nvector = self.grid_size
		width = self.ranges[0][1] - self.ranges[0][0]
		x = np.arange(0, Nvector)/float(Nvector) * width + self.ranges[0][0]# + width/(Nvector/2.)
		xmin, xmax = self.ranges[0]
		xmin, xmax = self.ranges[0]
		if self.ranges_show[0] is None:
			self.ranges_show[0] = xmin, xmax

		self.delta = (xmax - xmin) / self.grid_size
		self.centers = (np.arange(self.grid_size)+0.5) * self.delta + xmin

		logger.debug("expr for amplitude: %r" % self.amplitude_expression)
		grid_map = self.create_grid_map(self.grid_size, False)
		amplitude = self.eval_amplitude(self.amplitude_expression, locals=grid_map)
		use_selection = self.dataset.mask is not None
		if use_selection:
			grid_map_selection = self.create_grid_map(self.grid_size, True)
			amplitude_selection = self.eval_amplitude(self.amplitude_expression, locals=grid_map_selection)

		if use_selection:
			self.axes.bar(self.centers, amplitude, width=self.delta, align='center')
			self.axes.bar(self.centers, amplitude_selection, width=self.delta, align='center', color="red", alpha=0.8)
		else:
			self.axes.bar(self.centers, amplitude, width=self.delta, align='center')

		if self.range_level is None:
			if self.weight_expression:
				self.range_level = np.nanmin(amplitude) * 1.1, np.nanmax(amplitude) * 1.1
			else:
				self.range_level = 0, np.nanmax(amplitude) * 1.1

		if 0:
			amplitude = self.counts
			logger.debug("expr for amplitude: %r" % self.amplitude_expression)
			if self.amplitude_expression is not None:
				#locals = {"counts":self.counts, "counts_weights":self.counts_weights}
				locals = {"counts": self.counts, "weighted": self.counts_weights}
				locals["x"] = x
				if self.counts_weights is not None:
					locals["average"] = self.counts_weights/self.counts
				else:
					locals["average"] = None
				globals = np.__dict__
				amplitude = eval(self.amplitude_expression, globals, locals)

			if self.range_level is None:
				if self.weight_expression:
					self.range_level = np.nanmin(amplitude) * 1.1, np.nanmax(amplitude) * 1.1
				else:
					self.range_level = 0, np.nanmax(amplitude) * 1.1


			index = self.dataset.selected_row_index
			if index is not None and self.selected_point is None:
				logger.debug("point selected but after computation")
				# TODO: optimize
				# TODO: optimize
				def find_selected_point(info, block):
					if index >= info.i1 and index < info.i2: # selected point is in this block
						self.selected_point = block[index-info.i1]
				self.dataset.evaluate(find_selected_point, *self.expressions, **self.getVariableDict())

			if self.selected_point is not None:
				#x = self.getdatax()[self.dataset.selected_row_index]
				print "drawing vline at", self.selected_point
				self.axes.axvline(self.selected_point, color="red")

		self.axes.set_xlabel(self.expressions[0])
		xmin_show, xmax_show = self.ranges_show[0]
		print "plot limits:", xmin_show, xmax_show
		self.axes.set_xlim(xmin_show, xmax_show)
		ymin_show, ymax_show = self.range_level
		print "level limits:", ymin_show, ymax_show
		if not self.weight_expression:
			self.axes.set_ylabel("counts")
		else:
			self.axes.set_ylabel(self.weight_expression)
		self.axes.set_ylim(ymin_show, ymax_show)
		if not self.action_mini_mode_ultra.isChecked():
			self.fig.tight_layout(pad=0.0)
		self.canvas.draw()
		self.update()
		self.message("plotting %.2fs" % (time.time() - t0), index=100)


class ScatterPlotDialog(PlotDialog):
	names = "heatmap,density2d,2d"
	def __init__(self, parent, jobsManager, dataset, xname=None, yname=None, **options):
		super(ScatterPlotDialog, self).__init__(parent, jobsManager, dataset, [xname, yname], "X Y".split(), **options)

	def error_in_field(self, widget, exception):
		self.current_tooltip = QtGui.QToolTip.showText(widget.mapToGlobal(QtCore.QPoint(0, 0)), "Error: " + str(exception), widget)
		self.current_tooltip = QtGui.QToolTip.showText(widget.mapToGlobal(QtCore.QPoint(0, 0)), "Error: " + str(exception), widget)


	def calculate_visuals(self, info, blockx, blocky, weights_block, weights_x_block, weights_y_block, weights_xy_block, compute_counter=None):
		if compute_counter < self.compute_counter:
			print compute_counter, self.compute_counter
			print "STOP " * 100
			return True
		if info.error:
			self.message(info.error_text, index=-2)
			return

		elapsed = time.time() - info.time_start
		self.message("computation at %.2f%% (%fs)" % (info.percentage, elapsed), index=20)
		QtCore.QCoreApplication.instance().processEvents()
		self.expression_error = False

		N = self.grid_size
		Nvector = 32
		mask = self.dataset.mask
		if info.first:
			self.counts = np.zeros((N,) * self.dimensions, dtype=np.float64)
			self.counts_weights = None
			self.counts_x_weights = None
			self.counts_y_weights = None
			self.counts_xy_weights = None
			self.counts_xy = None
			if weights_block is not None:
				self.counts_weights = np.zeros((N,) * self.dimensions, dtype=np.float64)
			if weights_x_block is not None:
				self.counts_x_weights = np.zeros((Nvector,) * self.dimensions, dtype=np.float64)
			if weights_y_block is not None:
				self.counts_y_weights = np.zeros((Nvector,) * self.dimensions, dtype=np.float64)
			if weights_xy_block is not None:
				self.counts_xy_weights = np.zeros((Nvector,) * self.dimensions, dtype=np.float64)
			if weights_x_block is not None or weights_y_block is not None:
				self.counts_xy = np.zeros((Nvector,) * self.dimensions, dtype=np.float64)

			self.selected_point = None
			if mask is not None:
				self.counts_mask = np.zeros((N,) * self.dimensions, dtype=np.float64) #mab.utils.numpy.mmapzeros((128), dtype=np.float64)
				self.counts_weights_mask = None
				if weights_block is not None:
					self.counts_weights_mask = np.zeros((N,) * self.dimensions, dtype=np.float64)
			else:
				self.counts_mask = None
				self.counts_weights_mask = None





		xmin, xmax = self.ranges[0]
		ymin, ymax = self.ranges[1]
		for i in range(self.dimensions):
			if self.ranges_show[i] is None:
				self.ranges_show[i] = self.ranges[i]

		if self.aspect is not None:
			centers = [(range_[1] + range_[0])/2 for range_ in self.ranges_show]
			widths = [abs(range_[1] - range_[0]) for range_ in self.ranges_show] # TODO: should we use abs with flipped axes
			width, height = widths[:2]
			current_aspect = width/height
			#if current_aspect > self.aspect:
			logger.debug("ranges_show were: %r (width/height=%r/%r)"  % (self.ranges_show, width, height))
			#if current_aspect < 1:
			height = width/self.aspect
			#else:
			#width = self.aspect * height
			#else:
			self.ranges_show[0] = centers[0]-width/2,centers[0]+width/2
			self.ranges_show[1] = centers[1]-height/2,centers[1]+height/2
			self.ranges = [list(k) for k in self.ranges_show]
			logger.debug("ranges_show are: %r (width/height=%r/%r)"  % (self.ranges_show, width, height))



		index = self.dataset.selected_row_index
		if index is not None:
			if index >= info.i1 and index < info.i2: # selected point is in this block
				self.selected_point = blockx[index-info.i1], blocky[index-info.i1]

		t0 = time.time()
		#histo2d(blockx, blocky, self.counts, *self.ranges)
		ranges = []
		for minimum, maximum in self.ranges:
			ranges.append(minimum)
			if minimum == maximum:
				maximum += 1
			ranges.append(maximum)
		if 1:
			args = blockx, blocky, self.counts, ranges
			#gavi.histogram.hist2d(blockx, blocky, self.counts, *ranges)
			#subspacefind.histogram2d(blockx, blocky, self.counts, *ranges)
			if 1:
				sub_counts = np.zeros((self.pool.nthreads, N, N), dtype=np.float64)
				def subblock(index, sub_i1, sub_i2):
					subspacefind.histogram2d(blockx[sub_i1:sub_i2], blocky[sub_i1:sub_i2], None, sub_counts[index], *(ranges + [self.xoffset, self.yoffset]))
				self.pool.run_blocks(subblock, info.size)
				self.counts += np.sum(sub_counts, axis=0)
			else:
				subspacefind.histogram2d(blockx, blocky, None, self.counts, *(ranges + [self.xoffset, self.yoffset]))



			if weights_block is not None:
				args = blockx, blocky, weights_block, self.counts, ranges
				#gavi.histogram.hist2d_weights(blockx, blocky, self.counts_weights, weights_block, *ranges)
				if 1:
					sub_counts = np.zeros((self.pool.nthreads, N, N), dtype=np.float64)
					def subblock(index, sub_i1, sub_i2):
						subspacefind.histogram2d(blockx[sub_i1:sub_i2], blocky[sub_i1:sub_i2], weights_block[sub_i1:sub_i2], sub_counts[index], *(ranges + [self.xoffset, self.yoffset]))
					self.pool.run_blocks(subblock, info.size)
					self.counts_weights += np.sum(sub_counts, axis=0)
				else:
					subspacefind.histogram2d(blockx, blocky, weights_block, self.counts_weights, *(ranges + [self.xoffset, self.yoffset]))
			if mask is None:
				for counts_weighted, weight_block in [(self.counts_x_weights, weights_x_block), (self.counts_y_weights, weights_y_block), (self.counts_xy_weights, weights_xy_block)]:
					if weight_block is not None:
						sub_counts = np.zeros((self.pool.nthreads, Nvector, Nvector), dtype=np.float64)
						def subblock(index, sub_i1, sub_i2):
							subspacefind.histogram2d(blockx[sub_i1:sub_i2], blocky[sub_i1:sub_i2], weight_block[sub_i1:sub_i2], sub_counts[index], *(ranges + [self.xoffset, self.yoffset]))
						self.pool.run_blocks(subblock, info.size)
						counts_weighted += np.sum(sub_counts, axis=0)

		if weights_x_block is not None or weights_y_block is not None:
			if mask is None:
				#subspacefind.histogram2d(blockx, blocky, None, self.counts_xy, *(ranges + [self.xoffset, self.yoffset]))
				sub_counts = np.zeros((self.pool.nthreads, Nvector, Nvector), dtype=np.float64)
				def subblock(index, sub_i1, sub_i2):
					subspacefind.histogram2d(blockx[sub_i1:sub_i2], blocky[sub_i1:sub_i2], None, sub_counts[index], *(ranges + [self.xoffset, self.yoffset]))
				self.pool.run_blocks(subblock, info.size)
				self.counts_xy += np.sum(sub_counts, axis=0)

			else:
				subsetx = blockx[mask[info.i1:info.i2]]
				subsety = blocky[mask[info.i1:info.i2]]
				#subspacefind.histogram2d(subsetx, subsety, None, self.counts_xy, *(ranges + [self.xoffset, self.yoffset]))
				#subspacefind.histogram2d(blockx, blocky, None, self.counts_xy, *(ranges + [self.xoffset, self.yoffset]))
				sub_counts = np.zeros((self.pool.nthreads, Nvector, Nvector), dtype=np.float64)
				def subblock(index, sub_i1, sub_i2):
					subspacefind.histogram2d(subsetx[sub_i1:sub_i2], subsety[sub_i1:sub_i2], None, sub_counts[index], *(ranges + [self.xoffset, self.yoffset]))
				self.pool.run_blocks(subblock, len(subsetx))
				self.counts_xy += np.sum(sub_counts, axis=0)

		if mask is not None:
			subsetx = blockx[mask[info.i1:info.i2]]
			subsety = blocky[mask[info.i1:info.i2]]
			#print subx, suby, mask[info.i1:info.i2]
			#histo2d(subsetx, subsety, self.counts_mask, *self.ranges)
			#gavi.histogram.hist2d(subsetx, subsety, self.counts_mask, *ranges)

			sub_counts = np.zeros((self.pool.nthreads, N, N), dtype=np.float64)
			def subblock(index, sub_i1, sub_i2):
				subspacefind.histogram2d(subsetx[sub_i1:sub_i2], subsety[sub_i1:sub_i2], None, sub_counts[index], *(ranges + [self.xoffset, self.yoffset]))
			self.pool.run_blocks(subblock, len(subsetx))
			self.counts_mask += np.sum(sub_counts, axis=0)
			#else:
			#	subspacefind.histogram2d(subsetx, subsety, None, self.counts_mask, *ranges)

			if weights_block is not None:
				subset_weights = weights_block[mask[info.i1:info.i2]]
				#gavi.histogram.hist2d_weights(subsetx, subsety, subset_weights, self.counts_weights_mask, *ranges)
				#subspacefind.histogram2d(subsetx, subsety, subset_weights, self.counts_weights_mask, *ranges)
				sub_counts = np.zeros((self.pool.nthreads, N, N), dtype=np.float64)
				def subblock(index, sub_i1, sub_i2):
					subspacefind.histogram2d(subsetx[sub_i1:sub_i2], subsety[sub_i1:sub_i2], subset_weights[sub_i1:sub_i2], sub_counts[index], *(ranges + [self.xoffset, self.yoffset]))
				self.pool.run_blocks(subblock, len(subsetx))
				self.counts_weights_mask += np.sum(sub_counts, axis=0)

			for counts_weighted, weight_block in [(self.counts_x_weights, weights_x_block), (self.counts_y_weights, weights_y_block), (self.counts_xy_weights, weights_xy_block)]:
				if weight_block is not None:
					weights_block_mask = weight_block[mask[info.i1:info.i2]]
					sub_counts = np.zeros((self.pool.nthreads, Nvector, Nvector), dtype=np.float64)
					def subblock(index, sub_i1, sub_i2):
						subspacefind.histogram2d(subsetx[sub_i1:sub_i2], subsety[sub_i1:sub_i2], weights_block_mask[sub_i1:sub_i2], sub_counts[index], *(ranges + [self.xoffset, self.yoffset]))
					self.pool.run_blocks(subblock, len(subsetx))
					counts_weighted += np.sum(sub_counts, axis=0)

		if info.last:
			elapsed = time.time() - info.time_start
			self.message("computation %.2fs" % (elapsed), index=20)
			self.message(None, index=-2) # clear error
			if self.show_disjoined:
				self.counts = gavi.kld.to_disjoined(self.counts)
				if self.counts_mask is not None:
					self.counts_mask = gavi.kld.to_disjoined(self.counts_mask)
				if self.counts_x_weights is not None:
					self.counts_x_weights = gavi.kld.to_disjoined(self.counts_x_weights)
				if self.counts_y_weights is not None:
					self.counts_y_weights = gavi.kld.to_disjoined(self.counts_y_weights)
				if self.counts_xy_weights is not None:
					self.counts_xy_weights = gavi.kld.to_disjoined(self.counts_xy_weights)



	def _afterCanvas(self, layout):
		self.addToolbar2(layout)
		super(ScatterPlotDialog, self).afterCanvas(layout)


	def plot(self):
		self.axes.cla()
		#extent =
		#ranges = np.nanmin(datax), np.nanmax(datax), np.nanmin(datay), np.nanmax(datay)
		if 1:
			ranges = []
			logger.debug("self.ranges == %r" % (self.ranges, ))
			for minimum, maximum in self.ranges:
				ranges.append(minimum)
				ranges.append(maximum)


			#amplitude = self.grids.grids["counts"].get_data(self.gridsize)

			logger.debug("expr for amplitude: %r" % self.amplitude_expression)
			grid_map = self.create_grid_map(self.grid_size, False)
			amplitude = self.eval_amplitude(self.amplitude_expression, locals=grid_map)
			print "TOTAL", np.sum(amplitude)
			use_selection = self.dataset.mask is not None
			if use_selection:
				grid_map_selection = self.create_grid_map(self.grid_size, True)
				amplitude_selection = self.eval_amplitude(self.amplitude_expression, locals=grid_map_selection)


		if self.action_display_current == self.action_display_mode_both:
			self.axes.imshow(self.contrast(amplitude), origin="lower", extent=ranges, alpha=0.4 if use_selection else 1.0, cmap=self.colormap)
			if use_selection:
				self.axes.imshow(self.contrast(amplitude_selection), origin="lower", extent=ranges, alpha=1, cmap=self.colormap)
		if self.action_display_current == self.action_display_mode_full:
			self.axes.imshow(self.contrast(amplitude), origin="lower", extent=ranges, cmap=self.colormap)
		if self.action_display_current == self.action_display_mode_selection:
			if self.counts_mask is not None:
				self.axes.imshow(self.contrast(amplitude_mask), origin="lower", extent=ranges, alpha=1, cmap=self.colormap)
		if 1:
			#locals = {key:None if grid is None else gavifast.resize(grid, 64) for key, grid in locals}
			locals = {}
			for name in self.grids.grids.keys():
				grid = self.grids.grids[name]
				if name == "counts" or (grid.weight_expression is not None and len(grid.weight_expression) > 0):
					if grid.max_size >= self.vector_grid_size:
						locals[name] = grid.get_data(self.vector_grid_size, use_selection)
				else:
					locals[name] = None

			if 1:
				grid_map_vector = self.create_grid_map(self.vector_grid_size, use_selection)
				if grid_map_vector["weightx"] is not None and grid_map_vector["weighty"] is not None:
					mask = grid_map_vector["counts"] > 0
					x = grid_map_vector["x"]
					y = grid_map_vector["y"]
					x2d, y2d = np.meshgrid(x, y)
					vx = self.eval_amplitude("weightx/counts", locals=grid_map_vector)
					vy = self.eval_amplitude("weighty/counts", locals=grid_map_vector)
					meanvx = 0 if self.vectors_subtract_mean is False else vx[mask].mean()
					meanvy = 0 if self.vectors_subtract_mean is False else vy[mask].mean()
					vx -= meanvx
					vy -= meanvy
					if grid_map_vector["weightz"] is not None and self.vectors_color_code_3rd:
						colors = self.eval_amplitude("weightz/counts", locals=grid_map_vector)
						self.axes.quiver(x2d[mask], y2d[mask], vx[mask], vy[mask], colors[mask], cmap=self.colormap_vector)#, scale=1)
					else:
						self.axes.quiver(x2d[mask], y2d[mask], vx[mask], vy[mask], color="black")
						colors = None
				#print "min", U[mask].min(), V[mask].min()
				#print "max", U[mask].max(), V[mask].max()
				#self.axes.quiver(x, y, U, V)
		if self.action_display_current == self.action_display_mode_both_contour:
			#self.axes.imshow(amplitude, origin="lower", extent=ranges, alpha=1 if self.counts_mask is None else 0.4, cmap=cm_plusmin)
			#self.axes.contour(amplitude, origin="lower", extent=ranges, levels=levels, linewidths=2, colors="red")
			self.axes.imshow(amplitude, origin="lower", extent=ranges, cmap=self.colormap)
			if self.counts_mask is not None:
				values = amplitude_mask[~np.isinf(amplitude_mask)]
				print values
				levels = np.linspace(values.min(), values.max(), 5)
				print "levels", levels
				#self.axes.imshow(amplitude_mask, origin="lower", extent=ranges, alpha=1, cmap=cm_plusmin)
				self.axes.contour(amplitude_mask, origin="lower", extent=ranges, levels=levels, linewidths=2, colors="red")

		for callback in self.plugin_grids_draw:
			callback(self.axes, grid_map, grid_map_vector)


		if self.aspect is None:
			self.axes.set_aspect('auto')
		else:
			self.axes.set_aspect(self.aspect)
			#if self.dataset.selected_row_index is not None:
				#self.axes.autoscale(False)
		index = self.dataset.selected_row_index
		if 0:
			if index is not None and self.selected_point is None:
				logger.debug("point selected but after computation")
				# TODO: optimize
				def find_selected_point(info, blockx, blocky):
					if index >= info.i1 and index < info.i2: # selected point is in this block
						self.selected_point = blockx[index-info.i1], blocky[index-info.i1]
				self.dataset.evaluate(find_selected_point, *self.expressions, **self.getVariableDict())


			if self.selected_point:
				#x, y = self.getdatax()[self.dataset.selected_row_index],  self.getdatay()[self.dataset.selected_row_index]
				x, y = self.selected_point
				print "drawing selected point at", x, y
				self.axes.scatter([x], [y], color='red') #, scalex=False, scaley=False)
			#if dataxsel is not None:
			#	self.axes.scatter(dataxsel, dataysel)
		self.axes.set_xlabel(self.expressions[0])
		self.axes.set_ylabel(self.expressions[1])
		self.axes.set_xlim(*self.ranges_show[0])
		self.axes.set_ylim(*self.ranges_show[1])
		#self.fig.texts = []
		title_text = self.title_expression.format(**self.getVariableDict())
		if hasattr(self, "title"):
			self.title.set_text(title_text)
		else:
			self.title = self.fig.suptitle(title_text)
		if not self.action_mini_mode_ultra.isChecked():
			self.fig.tight_layout(pad=0.0)#1.008) #pad=pad, h_pad=h_pad, w_pad=w_pad, rect=rect)
		#self.fig.tight_layout(pad=0.01)#1.008) #pad=pad, h_pad=h_pad, w_pad=w_pad, rect=rect)
		self.fig.tight_layout()#1.008) #pad=pad, h_pad=h_pad, w_pad=w_pad, rect=rect)
		self.canvas.draw()
		self.update()
		if self.first_time:
			self.first_time = False
			if "filename" in self.options:
				self.filename_figure_last = self.options["filename"]
				self.fig.savefig(self.filename_figure_last)



class ScatterPlotMatrixDialog(PlotDialog):
	def __init__(self, parent, jobsManager, dataset, expressions):
		super(ScatterPlotMatrixDialog, self).__init__(parent, jobsManager, dataset, list(expressions), "X Y Z W V U T S R Q P".split()[:len(expressions)])

	def getAxesList(self):
		return reduce(lambda x,y: x + y, self.axes_grid, [])

	def addAxes(self):
		self.axes_grid = [[None,] * self.dimensions for _ in range(self.dimensions)]
		index = 0
		for i in range(self.dimensions)[::1]:
			for j in range(self.dimensions)[::1]:
				index = ((self.dimensions-1)-j) * self.dimensions + i + 1
				axes = self.axes_grid[i][j] = self.fig.add_subplot(self.dimensions,self.dimensions,index)
#													   sharey=self.axes_grid[0][j] if j > 0 else None,
#													   sharex=self.axes_grid[i][0] if i > 0 else None
#													   )
				# store the axis index in matplotlib object
				axes.xaxis_index = i
				axes.yaxis_index = j
				if i > 0:
					axes.yaxis.set_visible(False)
					#for label in axes.get_yticklabels():
					#	label.set_visible(False)
					#axes.yaxis.offsetText.set_visible(False)
				if j > 0:
					axes.xaxis.set_visible(False)
					#for label in axes.get_xticklabels():
					#	label.set_visible(False)
					#axes.xaxis.offsetText.set_visible(False)
				self.axes_grid[i][j].hold(True)
				index += 1
		self.fig.subplots_adjust(hspace=0, wspace=0)

	def calculate_visuals(self, info, *blocks):
		data_blocks = blocks[:self.dimensions]
		if len(blocks) > self.dimensions:
			weights_block = blocks[self.dimensions]
		else:
			weights_block = None
		elapsed = time.time() - info.time_start
		self.message("computation %.2f%% (%f seconds)" % (info.percentage, elapsed), index=9)
		QtCore.QCoreApplication.instance().processEvents()
		self.expression_error = False

		N = self.grid_size
		mask = self.dataset.mask
		if info.first:
			self.counts = np.zeros((N,) * self.dimensions, dtype=np.float64)
			self.counts_weights = self.counts
			if weights_block is not None:
				self.counts_weights = np.zeros((N,) * self.dimensions, dtype=np.float64)

			self.selected_point = None
			if mask is not None:
				self.counts_mask = np.zeros((N,) * self.dimensions, dtype=np.float64) #mab.utils.numpy.mmapzeros((128), dtype=np.float64)
				self.counts_weights_mask = self.counts_mask
				if weights_block is not None:
					self.counts_weights_mask = np.zeros((N,) * self.dimensions, dtype=np.float64)
			else:
				self.counts_mask = None
				self.counts_weights_mask = None

		if info.error:
			print "error", info.error_text
			self.expression_error = True
			self.message(info.error_text)
			return


		xmin, xmax = self.ranges[0]
		ymin, ymax = self.ranges[1]
		for i in range(self.dimensions):
			if self.ranges_show[i] is None:
				self.ranges_show[i] = self.ranges[i]


		index = self.dataset.selected_row_index
		if index is not None:
			if index >= info.i1 and index < info.i2: # selected point is in this block
				self.selected_point = blockx[index-info.i1], blocky[index-info.i1]

		t0 = time.time()
		#histo2d(blockx, blocky, self.counts, *self.ranges)
		ranges = []
		for minimum, maximum in self.ranges:
			ranges.append(minimum)
			if minimum == maximum:
				maximum += 1
			ranges.append(maximum)
		try:
			args = data_blocks, self.counts, ranges
			if self.dimensions == 2:
				gavi.histogram.hist3d(data_blocks[0], data_blocks[1], self.counts, *ranges)
			if self.dimensions == 3:
				gavi.histogram.hist3d(data_blocks[0], data_blocks[1], data_blocks[2], self.counts, *ranges)
			if weights_block is not None:
				args = data_blocks, weights_block, self.counts, ranges
				gavi.histogram.hist2d_weights(blockx, blocky, self.counts_weights, weights_block, *ranges)
		except:
			raise
		print "it took", time.time()-t0

		if mask is not None:
			subsets = [block[mask[info.i1:info.i2]] for block in data_blocks]
			if self.dimensions == 2:
				gavi.histogram.hist2d(subsets[0], subsets[1], self.counts_weights_mask, *ranges)
			if self.dimensions == 3:
				gavi.histogram.hist3d(subsets[0], subsets[1], subsets[2], self.counts_weights_mask, *ranges)
			if weights_block is not None:
				subset_weights = weights_block[mask[info.i1:info.i2]]
				if self.dimensions == 2:
					gavi.histogram.hist2d_weights(subsets[0], subsets[1], self.counts_weights_mask, subset_weights, *ranges)
				if self.dimensions == 3:
					gavi.histogram.hist3d_weights(subsets[0], subsets[1], subsets[2], self.counts_weights_mask, subset_weights, *ranges)
		if info.last:
			elapsed = time.time() - info.time_start
			self.message("computation (%f seconds)" % (elapsed), index=9)


	def plot(self):
		t0 = time.time()
		#self.axes.cla()
		#extent =
		#ranges = np.nanmin(datax), np.nanmax(datax), np.nanmin(datay), np.nanmax(datay)
		ranges = []
		for minimum, maximum in self.ranges:
			ranges.append(minimum)
			ranges.append(maximum)

		amplitude = self.counts
		logger.debug("expr for amplitude: %r" % self.amplitude_expression)
		if self.amplitude_expression is not None:
			locals = {"counts":self.counts_weights, "counts1": self.counts}
			globals = np.__dict__
			amplitude = eval(self.amplitude_expression, globals, locals)
		print "amplitude", np.nanmin(amplitude), np.nanmax(amplitude)
		#if self.ranges_level[0] is None:
		#	self.ranges_level[0] = 0, amplitude.max() * 1.1


		def multisum(a, axes):
			correction = 0
			for axis in axes:
				a = np.sum(a, axis=axis-correction)
				correction += 1
			return a
		for i in range(self.dimensions):
			for j in range(self.dimensions):
				axes = self.axes_grid[i][j]
				ranges = self.ranges[i] + self.ranges[j]
				axes.clear()
				allaxes = range(self.dimensions)
				if 0 :#i > 0:
					for label in axes.get_yticklabels():
						label.set_visible(False)
					axes.yaxis.offsetText.set_visible(False)
				if 0: #j > 0:
					for label in axes.get_xticklabels():
						label.set_visible(False)
					axes.xaxis.offsetText.set_visible(False)
				if i != j:
					allaxes.remove(i)
					allaxes.remove(j)
					counts_mask = None
					counts = multisum(self.counts, allaxes)
					if self.counts_mask is not None:
						counts_mask = multisum(self.counts_mask, allaxes)
					if i > j:
						counts = counts.T
					axes.imshow(np.log10(counts), origin="lower", extent=ranges, alpha=1 if counts_mask is None else 0.4)
					if counts_mask is not None:
						if i > j:
							counts_mask = counts_mask.T
						axes.imshow(np.log10(counts_mask), origin="lower", extent=ranges)
					axes.set_aspect('auto')
					if self.dataset.selected_row_index is not None:
						#self.axes.autoscale(False)
						x, y = self.getdatax()[self.dataset.selected_row_index],  self.getdatay()[self.dataset.selected_row_index]
						print "drawing selected point at", x, y
						axes.scatter([x], [y], color='red') #, scalex=False, scaley=False)

					axes.set_xlim(self.ranges_show[i][0], self.ranges_show[i][1])
					axes.set_ylim(self.ranges_show[j][0], self.ranges_show[j][1])
				else:
					allaxes.remove(j)
					counts = multisum(self.counts, allaxes)
					N = len(counts)
					xmin, xmax = self.ranges[i]
					delta = (xmax - xmin) / N
					centers = np.arange(N) * delta + xmin

					#axes.autoscale(False)
					#P.hist(x, 50, normed=1, histtype='stepfilled')
					#values =
					if 1: #if self.counts_mask is None:
						axes.bar(centers, counts, width=delta, align='center')
					else:
						self.axes.bar(self.centers, self.counts, width=self.delta, align='center', alpha=0.5)
						self.axes.bar(self.centers, self.counts_mask, width=self.delta, align='center', color="red")
					axes.set_xlim(self.ranges_show[i][0], self.ranges_show[i][1])
					axes.set_ylim(0, np.max(counts)*1.1)

		if 0:

			self.axes.imshow(amplitude.T, origin="lower", extent=ranges, alpha=1 if self.counts_mask is None else 0.4, cmap=cm_plusmin)
			if 1:
				if self.counts_mask is not None:
					if self.amplitude_expression is not None:
						#locals = {"counts":self.counts_mask}
						locals = {"counts":self.counts_weights_mask, "counts1": self.counts_mask}
						globals = np.__dict__
						amplitude_mask = eval(self.amplitude_expression, globals, locals)
					self.axes.imshow(amplitude_mask.T, origin="lower", extent=ranges, alpha=1, cmap=cm_plusmin)
				#self.axes.imshow((I), origin="lower", extent=ranges)
			self.axes.set_aspect('auto')
				#if self.dataset.selected_row_index is not None:
					#self.axes.autoscale(False)
			index = self.dataset.selected_row_index
			if index is not None and self.selected_point is None:
				logger.debug("point selected but after computation")
				# TODO: optimize
				def find_selected_point(info, blockx, blocky):
					if index >= info.i1 and index < info.i2: # selected point is in this block
						self.selected_point = blockx[index-info.i1], blocky[index-info.i1]
				self.dataset.evaluate(find_selected_point, *self.expressions, **self.getVariableDict())


			if self.selected_point:
				#x, y = self.getdatax()[self.dataset.selected_row_index],  self.getdatay()[self.dataset.selected_row_index]
				x, y = self.selected_point
				print "drawing selected point at", x, y
				self.axes.scatter([x], [y], color='red') #, scalex=False, scaley=False)
			#if dataxsel is not None:
			#	self.axes.scatter(dataxsel, dataysel)
			self.axes.set_xlabel(self.expressions[0])
			self.axes.set_ylabel(self.expressions[0])
			self.axes.set_xlim(*self.ranges_show[0])
			self.axes.set_ylim(*self.ranges_show[1])
		self.canvas.draw()
		self.message("ploting %f" % (time.time() - t0), index=5)

time_previous = time.time()
time_start = time.time()
def timelog(msg, reset=False):
	global time_previous, time_start
	now = time.time()
	if reset:
		time_start = now
	T = now - time_start
	deltaT = now - time_previous
	print "*** TIMELOG: %s (T=%f deltaT=%f)" % (msg, T, deltaT)
	time_previous = now

class VolumeRenderingPlotDialog(PlotDialog):
	names = "volumerendering,3d"
	def __init__(self, parent, jobsManager, dataset, xname, yname, zname, **options):
		super(VolumeRenderingPlotDialog, self).__init__(parent, jobsManager, dataset, [xname, yname, zname], "X Y Z".split(), **options)

	def afterCanvas(self, layout):

		self.widget_volume = gavi.vaex.volumerendering.VolumeRenderWidget(self)
		self.layout_plot_region.insertWidget(0, self.widget_volume, 1)


		#self.addToolbar2(layout)
		super(VolumeRenderingPlotDialog, self).afterCanvas(layout)

	def getAxesList(self):
		#return reduce(lambda x,y: x + y, self.axes_grid, [])
		return [self.axis_top, self.axis_bottom]

	def add_pages(self, toolbox):
		self.frame_options_volume_rendering = QtGui.QFrame(self)

		toolbox.addItem(self.frame_options_volume_rendering, "Volume rendering")
		toolbox.setCurrentIndex(3)
		self.fill_page_volume_rendering(self.frame_options_volume_rendering)

	def addAxes(self):
		self.axes_grid = [[None,] * self.dimensions for _ in range(self.dimensions)]
		self.axis_top = self.fig.add_subplot(2,1,1)
		self.axis_bottom = self.fig.add_subplot(2,1,2)
		self.axis_top.xaxis_index = 0
		self.axis_top.yaxis_index = 1
		self.axis_bottom.xaxis_index = 0
		self.axis_bottom.yaxis_index = 2
		#self.fig.subplots_adjust(hspace=0, wspace=0)

	#def calculate_visuals(self, info, blockx=None, blocky=None, blockz=None, compute_counter=None):
	def calculate_visuals(self, info, blockx, blocky, blockz, weights_block, weights_x_block, weights_y_block, weights_xy_block, compute_counter=None):
		if compute_counter < self.compute_counter:
			print "STOP " * 100
			return True
		print "info", info

		blocks = [blockx, blocky, blockz]
		data_blocks = blocks[:self.dimensions]
		if len(blocks) > self.dimensions:
			weights_block = blocks[self.dimensions]
		else:
			weights_block = None
		elapsed = time.time() - info.time_start
		self.message("computation %.2f%% (%f seconds)" % (info.percentage, elapsed), index=9)
		QtCore.QCoreApplication.instance().processEvents()
		self.expression_error = False

		print "aap"

		N = self.grid_size
		mask = self.dataset.mask
		if info.first:
			self.counts = np.zeros((N,) * self.dimensions, dtype=np.float64)
			self.counts_weights = None
			if weights_block is not None:
				self.counts_weights = np.zeros((N,) * self.dimensions, dtype=np.float64)

			self.selected_point = None
			if mask is not None:
				self.counts_mask = np.zeros((N,) * self.dimensions, dtype=np.float64) #mab.utils.numpy.mmapzeros((128), dtype=np.float64)
				self.counts_weights_mask = None
				if weights_block is not None:
					self.counts_weights_mask = np.zeros((N,) * self.dimensions, dtype=np.float64)
			else:
				self.counts_mask = None
				self.counts_weights_mask = None

		if info.error:
			print "error", info.error_text
			self.expression_error = True
			self.message(info.error_text)
			return


		xmin, xmax = self.ranges[0]
		ymin, ymax = self.ranges[1]
		for i in range(self.dimensions):
			if self.ranges_show[i] is None:
				self.ranges_show[i] = self.ranges[i]


		print "noot"
		index = self.dataset.selected_row_index
		if index is not None:
			if index >= info.i1 and index < info.i2: # selected point is in this block
				self.selected_point = blockx[index-info.i1], blocky[index-info.i1]

		t0 = time.time()
		#histo2d(blockx, blocky, self.counts, *self.ranges)
		ranges = []
		for minimum, maximum in self.ranges:
			ranges.append(minimum)
			if minimum == maximum:
				maximum += 1
			ranges.append(maximum)
		print "mies"
		try:
			args = data_blocks, self.counts, ranges
			#if self.dimensions == 2:
			#	gavi.histogram.hist3d(data_blocks[0], data_blocks[1], self.counts, *ranges)
			#if self.dimensions == 3:
			#	#gavi.histogram.hist3d(data_blocks[0], data_blocks[1], data_blocks[2], self.counts, *ranges)
			gavifast.histogram3d(blockx, blocky, blockz, None, self.counts, *ranges)
			#if weights_block is not None:
			#	args = data_blocks, weights_block, self.counts, ranges
			#	gavi.histogram.hist2d_weights(blockx, blocky, self.counts_weights, weights_block, *ranges)
		except:
			print "args", args
			print blockx.shape, blockx.dtype
			print blocky.shape, blocky.dtype
			print self.counts.shape, self.counts.dtype
			raise
		print "it took", time.time()-t0
		print "mies2"

		if mask is not None:
			subsets = [block[mask[info.i1:info.i2]] for block in data_blocks]
			if self.dimensions == 2:
				gavi.histogram.hist2d(subsets[0], subsets[1], self.counts_weights_mask, *ranges)
			if self.dimensions == 3:
				gavi.histogram.hist3d(subsets[0], subsets[1], subsets[2], self.counts_mask, *ranges)
			if weights_block is not None:
				subset_weights = weights_block[mask[info.i1:info.i2]]
				if self.dimensions == 2:
					gavi.histogram.hist2d_weights(subsets[0], subsets[1], self.counts_weights_mask, subset_weights, *ranges)
				if self.dimensions == 3:
					gavi.histogram.hist3d_weights(subsets[0], subsets[1], subsets[2], self.counts_weights_mask, subset_weights, *ranges)
		if info.last:
			elapsed = time.time() - info.time_start
			self.message("computation (%f seconds)" % (elapsed), index=9)


	def plot(self):
		timelog("plot start", reset=False)
		t0 = time.time()
		if 1:
			ranges = []
			for minimum, maximum in self.ranges:
				ranges.append(minimum)
				ranges.append(maximum)

			timelog("creating grid map")
			grid_map = self.create_grid_map(self.grid_size, False)
			timelog("eval amplitude")
			amplitude = self.eval_amplitude(self.amplitude_expression, locals=grid_map)
			timelog("eval amplitude done")
			use_selection = self.dataset.mask is not None
			if use_selection:
				timelog("repeat for selection")
				grid_map_selection = self.create_grid_map(self.grid_size, True)
				amplitude_selection = self.eval_amplitude(self.amplitude_expression, locals=grid_map_selection)

			timelog("creating grid map vector")
			grid_map_vector = self.create_grid_map(self.vector_grid_size, use_selection)
			vector_grid = None
			vector_counts = grid_map_vector["counts"]
			vector_mask = vector_counts > 0
			if grid_map_vector["weightx"] is not None:
				vector_x = grid_map_vector["x"]
				vx = self.eval_amplitude("weightx/counts", locals=grid_map_vector)
			else:
				vector_x = None
				vx = None
			if grid_map_vector["weighty"] is not None:
				vector_y = grid_map_vector["y"]
				vy = self.eval_amplitude("weighty/counts", locals=grid_map_vector)
			else:
				vector_y = None
				vy = None
			if grid_map_vector["weightz"] is not None:
				vector_z = grid_map_vector["z"]
				vz = self.eval_amplitude("weightz/counts", locals=grid_map_vector)
			else:
				vector_z = None
				vz = None
			if vx is not None and vy is not None and vz is not None:
				timelog("making vector grid")
				vector_grid = np.zeros((4, ) + ((vx.shape[0],) * 3), dtype=np.float32)
				mask = vector_counts > 0
				meanvx = 0 if self.vectors_subtract_mean is False else vx[mask].mean()
				meanvy = 0 if self.vectors_subtract_mean is False else vy[mask].mean()
				meanvz = 0 if self.vectors_subtract_mean is False else vz[mask].mean()
				vector_grid[0] = vx - meanvx
				vector_grid[1] = vy - meanvy
				vector_grid[2] = vz - meanvz
				vector_grid[3] = vector_counts
				vector_grid = np.swapaxes(vector_grid, 0, 3)
				vector_grid = vector_grid * 1.
			timelog("setting grid")
			self.widget_volume.setGrid(amplitude_selection if use_selection else amplitude, vector_grid)
			timelog("grid")
			if 0:
				self.tool.grid = amplitude
				self.tool.update()
			
			#if self.ranges_level[0] is None:
			#	self.ranges_level[0] = 0, amplitude.max() * 1.1
			#return


			def multisum(a, axes):
				correction = 0
				for axis in axes:
					a = np.nansum(a, axis=axis-correction)
					correction += 1
				return a		
			axeslist = self.getAxesList()
			vector_values = [vx, vy, vz]
			vector_positions = [vector_x, vector_y, vector_z]
			for i in range(2):
					timelog("axis: " +str(i))
					axes = axeslist[i]
					i1 = 0
					i2 = i + 1
					i3 = 2- i
					ranges = list(self.ranges[i1]) + list(self.ranges[i2])
					axes.clear()
					allaxes = range(self.dimensions)
					if 0 :#i > 0:
						for label in axes.get_yticklabels():
							label.set_visible(False)
						axes.yaxis.offsetText.set_visible(False)
					if 0: #j > 0:
						for label in axes.get_xticklabels():
							label.set_visible(False)
						axes.xaxis.offsetText.set_visible(False)
					if 1:
						#print "axes", allaxes, i1, i2, i3, vector_values, vector_positions
						allaxes.remove(2-(0))
						allaxes.remove(2-(1+i))
						print "removed", allaxes
						counts_mask = None
						colors = "red green blue".split()
						axes.spines['bottom'].set_color(colors[i1])
						axes.spines['left'].set_color(colors[i2])
						linewidth = 2.
						axes.spines['bottom'].set_linewidth(linewidth)
						axes.spines['left'].set_linewidth(linewidth)

						grid_map_2d = {key:None if grid is None else (grid if grid.ndim != 3 else multisum(grid, allaxes)) for key, grid in grid_map.items()}
						amplitude = self.eval_amplitude(self.amplitude_expression, locals=grid_map_2d)
						if use_selection:
							grid_map_selection_2d = {key:None if grid is None else (grid if grid.ndim != 3 else multisum(grid, allaxes)) for key, grid in grid_map_selection.items()}
							amplitude_selection = self.eval_amplitude(self.amplitude_expression, locals=grid_map_selection_2d)

						axes.imshow(self.contrast(amplitude), origin="lower", extent=ranges, alpha=0.4 if use_selection else 1.0, cmap=self.colormap)
						if use_selection:
							axes.imshow(self.contrast(amplitude_selection), origin="lower", extent=ranges, alpha=1, cmap=self.colormap)

						#vector_positions1, vector_positions2,  = vector_positions[i1],  vector_positions[i2]
						#vector_values1, vector_values2 = vector_values[i1],  vector_values[i2]
						if vector_positions[i1] is not None and vector_positions[i2] is not None:
							print "drawing vectors"
							mask = multisum(vector_counts, allaxes) > 0
							x, y = np.meshgrid(vector_positions[i1], vector_positions[i2])
							U = multisum(vector_values[i1], allaxes)
							V = multisum(vector_values[i2], allaxes)

							if np.any(mask):
								meanU = 0 if self.vectors_subtract_mean is False else np.nanmean(U[mask])
								meanV = 0 if self.vectors_subtract_mean is False else np.nanmean(V[mask])
								U -= meanU
								V -= meanV

							if vector_positions[i3] is not None and self.vectors_color_code_3rd:
								print "with colors"
								W = multisum(vector_values[i3], allaxes)
								if np.any(mask):
									meanW = 0 if self.vectors_subtract_mean is False else np.nanmean(W[mask])
									W -= meanW
								#print U.shape, vector_mask.shape
								axes.quiver(x[mask], y[mask], U[mask], V[mask], W[mask], cmap=self.colormap_vector)
							else:
								print "without colors"
								axes.quiver(x[mask], y[mask], U[mask], V[mask], color="black")
	

						if 0: # TODO: self.dataset.selected_row_index is not None:
							#self.axes.autoscale(False)
							x, y = self.getdatax()[self.dataset.selected_row_index],  self.getdatay()[self.dataset.selected_row_index]
							print "drawing selected point at", x, y
							axes.scatter([x], [y], color='red') #, scalex=False, scaley=False)
					if self.aspect is None:
						axes.set_aspect('auto')
					else:
						axes.set_aspect(self.aspect)
						
					axes.set_xlim(self.ranges_show[i1][0], self.ranges_show[i1][1])
					axes.set_ylim(self.ranges_show[i2][0], self.ranges_show[i2][1])
					axes.set_xlabel(self.expressions[i1])
					axes.set_ylabel(self.expressions[i2])
			if 0:
					
				self.axes.imshow(amplitude.T, origin="lower", extent=ranges, alpha=1 if self.counts_mask is None else 0.4, cmap=cm_plusmin)
				if 1:
					if self.counts_mask is not None:
						if self.amplitude_expression is not None:
							#locals = {"counts":self.counts_mask}
							locals = {"counts":self.counts_weights_mask, "counts1": self.counts_mask}
							globals = np.__dict__
							amplitude_mask = eval(self.amplitude_expression, globals, locals)
						self.axes.imshow(amplitude_mask.T, origin="lower", extent=ranges, alpha=1, cmap=cm_plusmin)
					#self.axes.imshow((I), origin="lower", extent=ranges)
				self.axes.set_aspect('auto')
					#if self.dataset.selected_row_index is not None:
						#self.axes.autoscale(False)
				index = self.dataset.selected_row_index
				if index is not None and self.selected_point is None:
					logger.debug("point selected but after computation")
					# TODO: optimize
					def find_selected_point(info, blockx, blocky):
						if index >= info.i1 and index < info.i2: # selected point is in this block
							self.selected_point = blockx[index-info.i1], blocky[index-info.i1]
					self.dataset.evaluate(find_selected_point, *self.expressions, **self.getVariableDict())
					

				if self.selected_point:
					#x, y = self.getdatax()[self.dataset.selected_row_index],  self.getdatay()[self.dataset.selected_row_index]
					x, y = self.selected_point
					print "drawing selected point at", x, y
					self.axes.scatter([x], [y], color='red') #, scalex=False, scaley=False)
				#if dataxsel is not None:
				#	self.axes.scatter(dataxsel, dataysel)
				self.axes.set_xlabel(self.expressions[0])
				self.axes.set_ylabel(self.expressions[0])
				print "plot limits:", self.ranges
				self.axes.set_xlim(*self.ranges_show[0])
				self.axes.set_ylim(*self.ranges_show[1])
		self.canvas.draw()
		timelog("plot end")
		self.message("ploting %f" % (time.time() - t0), index=5)
		

class Rank1ScatterPlotDialog(ScatterPlotDialog):
	def __init__(self, parent, jobsManager, dataset, xname=None, yname=None):
		self.nSlices = dataset.rank1s[dataset.rank1s.keys()[0]].shape[0]
		self.serieIndex = dataset.selected_serie_index if dataset.selected_serie_index is not None else 0
		self.record_frames = False
		super(Rank1ScatterPlotDialog, self).__init__(parent, jobsManager, dataset, xname, yname)

	def getTitleExpressionList(self):
		#return []
		return ["%s: {%s: 4f}" % (name, name) for name in self.dataset.axis_names]
		
	def addToolbar2(self, layout, contrast=True, gamma=True):
		super(Rank1ScatterPlotDialog, self).addToolbar2(layout, contrast, gamma)
		self.action_save_frames = QtGui.QAction(QtGui.QIcon(iconfile('film')), '&Export frames', self)
		self.menu_save.addAction(self.action_save_frames)
		self.action_save_frames.triggered.connect(self.onActionSaveFrames)
		
	def onActionSaveFrames(self, ignore=None):
		import qt
		#directory = QtGui.QFileDialog.getExistingDirectory(self, "Choose where to save frames", "",  QtGui.QFileDialog.ShowDirsOnly | QtGui.QFileDialog.DontResolveSymlinks)
		#print directory
		directory = qt.getdir(self, "Choose where to save frames", "")
		self.frame_template = os.path.join(directory, "%s_{index:05}.png" % self.dataset.name)
		self.frame_template = qt.gettext(self, "template for frame filenames", "template:", self.frame_template)
		self.record_frames = True
		self.onPlayOnce()
		
	def plot(self):
		super(Rank1ScatterPlotDialog, self).plot()
		if self.record_frames:
			index = self.serieIndex
			path = self.frame_template.format(**locals())
			self.fig.savefig(path)
			if self.serieIndex == self.nSlices-1:
				self.record_frames = False
				

	def onSerieIndexSelect(self, serie_index):
		if serie_index != self.serieIndex: # avoid unneeded event
			self.serieIndex = serie_index
			self.seriesbox.setCurrentIndex(self.serieIndex)
		else:
			self.serieIndex = serie_index
		#print "%" * 200
		self.compute()
		#self.jobsM
		#self.plot()
	
		
	def getExpressionList(self):
		names = []
		for rank1name in self.dataset.rank1names:
			names.append(rank1name + "[index]")
		return names
	
	def getVariableDict(self):
		vars = {"index": self.serieIndex}
		for name in self.dataset.axis_names:
			vars[name] = self.dataset.axes[name][self.serieIndex]
		print "vars", vars
		return vars
		

	def _getVariableDictMinMax(self):
		return {"index": slice(None, None, None)}

	def afterCanvas(self, layout):
		super(Rank1ScatterPlotDialog, self).afterCanvas(layout)
		#return

		self.seriesbox = QtGui.QComboBox(self)
		self.seriesbox.addItems([str(k) for k in range(self.nSlices)])
		self.seriesbox.setCurrentIndex(self.serieIndex)
		self.seriesbox.currentIndexChanged.connect(self.onSerieIndex)
		
		self.grid_layout.addWidget(self.seriesbox, 10, 1)
		#self.form_layout = QtGui.QFormLayout(self)
		#self.form_layout.addRow("index", self.seriesbox)
		#self.buttonLoop = QtGui.QToolButton(self)
		#self.buttonLoop.setText("one loop")
		#self.buttonLoop.clicked.connect(self.onPlayOnce)
		#self.form_layout.addRow("movie", self.buttonLoop)
		#layout.addLayout(self.form_layout, 0)
		
	def onPlayOnce(self):
		#self.timer = QtCore.QTimer(self)
		#self.timer.timeout.connect(self.onNextFrame)
		self.delay = 10
		if not self.axis_lock:
			for i in range(self.dimensions):
				self.ranges[i] = None
			for i in range(self.dimensions):
				self.ranges_show[i] = None
		self.dataset.selectSerieIndex(0)
		self.jobsManager.execute()
		QtCore.QTimer.singleShot(self.delay if not self.record_frames else 0, self.onNextFrame);
		
	def onNextFrame(self, *args):
		#print args
		step = 1
		next = self.serieIndex +step
		if next >= self.nSlices:
			next = self.nSlices-1
		if not self.axis_lock:
			for i in range(self.dimensions):
				self.ranges[i] = None
			for i in range(self.dimensions):
				self.ranges_show[i] = None
		self.dataset.selectSerieIndex(next)
		self.jobsManager.execute()
		if self.serieIndex < self.nSlices-1 : # not last frame
			QtCore.QTimer.singleShot(self.delay, self.onNextFrame);
			
			
	def onSerieIndex(self, index):
		if index != self.dataset.selected_serie_index: # avoid unneeded event
			if not self.axis_lock:
				for i in range(self.dimensions):
					self.ranges[i] = None
				for i in range(self.dimensions):
					self.ranges_show[i] = None
			self.dataset.selectSerieIndex(index)
			#self.compute()
			self.jobsManager.execute()


