package dev.opensarthi.android

import android.os.Bundle
import android.util.Log
import com.getcapacitor.BridgeActivity
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch

/**
 * Main activity — extends Capacitor's BridgeActivity to host the React WebView.
 *
 * On create, it starts the Python FastAPI runtime in a background thread via RuntimeService.
 * The React WebView then connects to ws://127.0.0.1:8765/ws — same protocol as desktop.
 *
 * Runtime startup sequence:
 *   1. OpenSarthiApp.onCreate → Python.start() (Chaquopy)
 *   2. MainActivity.onCreate  → starts RuntimeService
 *   3. RuntimeService         → runs main_android.py (FastAPI on port 8765)
 *   4. React WebView          → connects to ws://127.0.0.1:8765/ws
 */
class MainActivity : BridgeActivity() {

    companion object {
        private const val TAG = "OpenSarthi"
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        AndroidVoiceBridge.init(this)
        startRuntimeService()
    }

    private fun startRuntimeService() {
        Log.i(TAG, "Starting OpenSarthi runtime service...")
        val intent = android.content.Intent(this, RuntimeService::class.java)
        if (android.os.Build.VERSION.SDK_INT >= android.os.Build.VERSION_CODES.O) {
            startForegroundService(intent)
        } else {
            startService(intent)
        }
    }
}
