import time
from PyQt4 import QtCore
from PyQt4 import QtGui
from PyQt4.QtCore import Qt

import logging
log = logging.getLogger(__name__)

def async(method, args, uid, readycb, errorcb=None, pingcb=None, description=""):
    """
    Asynchronously runs a task

    :param func method: the method to run in a thread
    :param object uid: a unique identifier for this task (used for verification)
    :param slot updatecb: the callback when data is receieved cb(uid, data)
    :param slot errorcb: the callback when there is an error cb(uid, errmsg)

    The uid option is useful when the calling code makes multiple async calls
    and the callbacks need some context about what was sent to the async method.
    For example, if you use this method to thread a long running database call
    and the user decides they want to cancel it and start a different one, the
    first one may complete before you have a chance to cancel the task.  In that
    case, the "readycb" will be called with the cancelled task's data.  The uid
    can be used to differentiate those two calls (ie. using the sql query).

    :returns: Request instance
    """
    request = Request(method, args, uid, readycb, errorcb, pingcb, description)
    QtCore.QThreadPool.globalInstance().start(request)
    return request

def get_kwargs(method):
    args = method.__code__.co_varnames[:method.__code__.co_argcount]
    num_kwargs = len(method.__defaults__) if method.__defaults__ else 0
    if num_kwargs < 1:
        return [ ]
    kwargs = args[-num_kwargs:] # because kwargs are last
    return kwargs

def has_kwarg(method, kwarg_name):
    return kwarg_name in get_kwargs(method)

class Request(QtCore.QRunnable):
    """
    A Qt object that represents an asynchronous task

    :param func method: the method to call
    :param list args: list of arguments to pass to method
    :param object uid: a unique identifier (used for verification)
    :param slot readycb: the callback used when data is receieved
    :param slot errorcb: the callback used when there is an error

    The uid param is sent to your error and update callbacks as the
    first argument. It's there to verify the data you're returning

    After created it should be used by invoking:

    .. code-block:: python

       task = Request(...)
       QtCore.QThreadPool.globalInstance().start(task)

    """
    PT_STARTED = 1
    PT_FAILED = -1
    PT_CANCELLED = -2
    PT_FINISHED = 100

    INSTANCES = []
    FINISHED = []
    def __init__(self, method, args, uid, readycb, errorcb=None, pingcb=None, description=""):
        super(Request, self).__init__()
        self.setAutoDelete(True)
        self.cancelled = False

        self.method = method
        self.args = args
        self.uid = uid
        self.dataReady = readycb
        self.dataError = errorcb
        self.dataPing = pingcb

        self.description = description
        self.status = None

        Request.INSTANCES.append(self)

        # release all of the finished tasks
        Request.FINISHED = []

    def run(self):
        """
        Method automatically called by Qt when the runnable is ready to run.
        This will run in a separate thread.
        """
        # this allows us to "cancel" queued tasks if needed, should be done
        # on shutdown to prevent the app from hanging
        if self.cancelled:
            self.cleanup()
            return

        # runs in a separate thread, for proper async signal/slot behavior
        # the object that emits the signals must be created in this thread.
        # Its not possible to run grabber.moveToThread(QThread.currentThread())
        # so to get this QObject to properly exhibit asynchronous
        # signal and slot behavior it needs to live in the thread that
        # we're running in, creating the object from within this thread
        # is an easy way to do that.
        grabber = Requester()
        grabber.Loaded.connect(self.dataReady, Qt.QueuedConnection)
        if self.dataError is not None:
            grabber.Error.connect(self.dataError, Qt.QueuedConnection)
        if self.dataPing is not None:
            grabber.Ping.connect(self.dataPing, Qt.QueuedConnection)

        try:
            grabber.Ping.emit(self.uid, Request.PT_STARTED, 0)
            if has_kwarg(self.method, "ping_callback"):
                result = self.method(*self.args, ping_callback=grabber.Ping)
            else:
                result = self.method(*self.args)

            if not(self.cancelled):
                grabber.Loaded.emit(self.uid, result)
                grabber.Ping.emit(self.uid, Request.PT_FINISHED, 0)
            else:
                grabber.Ping.emit(self.uid, Request.PT_CANCELLED, 0)

        except Exception as error:
            import traceback
            traceback.print_exc()
            if not(self.cancelled):
                grabber.Error.emit(self.uid, error)
                grabber.Ping.emit(self.uid, Request.PT_FAILED, 0)
            else:
                grabber.Ping.emit(self.uid, Request.PT_CANCELLED, 0)

        finally:
            self.cleanup(grabber)



    def cancel(self):
        self.cancelled = True
        #self.cleanup()

    def cleanup(self, grabber=None):
        # remove references to any object or method for proper ref counting
        self.method = None
        self.args = None
        self.uid = None
        self.dataReady = None
        self.dataError = None
        self.description = None

        if grabber is not None:
            grabber.deleteLater()

        # make sure this python obj gets cleaned up
        self.remove()

    def remove(self):
        try:
            Request.INSTANCES.remove(self)

            # when the next request is created, it will clean this one up
            # this will help us avoid this object being cleaned up
            # when it's still being used
            Request.FINISHED.append(self)
        except ValueError:
            # there might be a race condition on shutdown, when shutdown()
            # is called while the thread is still running and the instance
            # has already been removed from the list
            return

    @staticmethod
    def shutdown(timeout=10):
        for inst in Request.INSTANCES:
            inst.cancelled = True
        #Request.INSTANCES = []
        #Request.FINISHED = []
        Request.wait_join(timeout)

    @staticmethod
    def wait_join(timeout=10):
        while len(Request.INSTANCES) > 0:
            print("Waiting for", Request.top())
            time.sleep(1)
            timeout -= 1
            if timeout == 0:
                return False
        return True

    @staticmethod
    def top():
        r = [ ]
        for inst in Request.INSTANCES:
            r.append( (inst.cancelled, inst.description, inst.method.__name__ if inst.method else "") )
        return r

class Requester(QtCore.QObject):
    """
    A simple object designed to be used in a separate thread to allow
    for asynchronous data fetching
    """

    #
    # Signals
    #

    Ping = QtCore.pyqtSignal(int, int, object)
    """
    Emitted during request lifetime

    :param str uid: an id to identify this request
    :param int ping_type:
    :param int ping_data:
    """

    Error = QtCore.pyqtSignal(int, object)
    """
    Emitted if the fetch fails for any reason

    :param str uid: an id to identify this request
    :param str error: the error message
    """

    Loaded = QtCore.pyqtSignal(int, object)
    """
    Emitted whenever data comes back successfully

    :param str uid: an id to identify this request
    :param list data: the json list returned from the GET
    """

    NetworkConnectionError = QtCore.pyqtSignal(str)
    """
    Emitted when the task fails due to a network connection error

    :param str message: network connection error message
    """

    def __init__(self, parent=None):
        super(Requester, self).__init__(parent)


class ExampleObject(QtCore.QObject):
    def __init__(self, parent=None):
        super(ExampleObject, self).__init__(parent)
        self.uid = 0
        self.request = None
        self.description = ""

    def ready_callback(self, uid, result):
        if uid != self.uid:
            return
        print( "Data ready from %s: %s" % (uid, result))

    def error_callback(self, uid, error):
        if uid != self.uid:
            return
        print( "Data error from %s: %s" % (uid, error))

    def fetch(self):
        if self.request is not None:
            # cancel any pending requests
            self.request.cancelled = True
            self.request = None

        self.uid += 1
        self.request = async(slow_method, ["arg1", "arg2"], self.uid,
                             self.ready_callback,
                             self.error_callback,
                             self.ping_callback,
                             self.description)


def slow_method(arg1, arg2):
    print( "Starting slow method")
    time.sleep(1)
    return arg1 + arg2


if __name__ == "__main__":
    import sys
    app = QtGui.QApplication(sys.argv)

    obj = ExampleObject()

    dialog = QtGui.QDialog()
    layout = QtGui.QVBoxLayout(dialog)
    button = QtGui.QPushButton("Generate", dialog)
    progress = QtGui.QProgressBar(dialog)
    progress.setRange(0, 0)
    layout.addWidget(button)
    layout.addWidget(progress)
    button.clicked.connect(obj.fetch)
    dialog.show()

    app.exec_()
    app.deleteLater() # avoids some QThread messages in the shell on exit
    # cancel all running tasks avoid QThread/QTimer error messages
    # on exit
    Request.shutdown()