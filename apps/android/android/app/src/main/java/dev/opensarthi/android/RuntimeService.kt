package dev.opensarthi.android

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.Service
import android.content.Intent
import android.os.Build
import android.os.IBinder
import android.util.Log
import com.chaquo.python.Python
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.launch

/**
 * RuntimeService — runs the Python FastAPI server in a foreground service.
 *
 * Why foreground service?
 *   Android kills background services aggressively. The FastAPI server must
 *   stay alive as long as the user is in the app (and optionally when backgrounded).
 *   A foreground service with a persistent notification is the correct pattern.
 *
 * How Chaquopy runs the server:
 *   Python.getInstance().getModule("main_android").callAttr("start_server")
 *   This calls start_server() in runtime/main_android.py which starts uvicorn
 *   on port 8765 in a background asyncio thread.
 */
class RuntimeService : Service() {

    companion object {
        private const val TAG = "OpenSarthiRuntime"
        private const val NOTIFICATION_ID = 1001
        private const val CHANNEL_ID = "opensarthi_runtime"
        private const val RUNTIME_PORT = 8765
    }

    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.IO)
    private var runtimeStarted = false

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onCreate() {
        super.onCreate()
        createNotificationChannel()
        startForeground(NOTIFICATION_ID, buildNotification())
        startPythonRuntime()
    }

    private fun startPythonRuntime() {
        if (runtimeStarted) return
        runtimeStarted = true

        scope.launch {
            try {
                Log.i(TAG, "Starting Python FastAPI runtime on port $RUNTIME_PORT...")
                val py = Python.getInstance()
                // main_android.py is in runtime/ which is included as a Python source dir
                val mainModule = py.getModule("main_android")
                // Blocking call — start_server() runs uvicorn and blocks until service stops
                mainModule.callAttr("start_server", RUNTIME_PORT)
            } catch (e: Exception) {
                Log.e(TAG, "Python runtime failed to start: ${e.message}", e)
            }
        }
    }

    override fun onDestroy() {
        super.onDestroy()
        try {
            val py = Python.getInstance()
            py.getModule("main_android").callAttr("stop_server")
        } catch (e: Exception) {
            Log.w(TAG, "Error stopping Python server: ${e.message}")
        }
        Log.i(TAG, "RuntimeService destroyed")
    }

    private fun createNotificationChannel() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            val channel = NotificationChannel(
                CHANNEL_ID,
                "OpenSarthi AI Runtime",
                NotificationManager.IMPORTANCE_LOW
            ).apply {
                description = "Keeps the AI agent runtime active"
                setShowBadge(false)
            }
            val manager = getSystemService(NotificationManager::class.java)
            manager.createNotificationChannel(channel)
        }
    }

    private fun buildNotification(): Notification {
        return if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            Notification.Builder(this, CHANNEL_ID)
                .setContentTitle("OpenSarthi")
                .setContentText("AI runtime active")
                .setSmallIcon(android.R.drawable.ic_dialog_info)
                .setOngoing(true)
                .build()
        } else {
            @Suppress("DEPRECATION")
            Notification.Builder(this)
                .setContentTitle("OpenSarthi")
                .setContentText("AI runtime active")
                .setSmallIcon(android.R.drawable.ic_dialog_info)
                .setOngoing(true)
                .build()
        }
    }
}
