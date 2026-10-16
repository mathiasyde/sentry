package com.example.bachelorproject

import android.Manifest
import android.content.Context
import android.content.pm.PackageManager
import android.graphics.Bitmap
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.util.Base64
import android.util.Log
import android.webkit.JavascriptInterface
import android.webkit.WebChromeClient
import android.webkit.WebView
import android.webkit.WebView.getCurrentWebViewPackage
import android.webkit.WebView.setWebContentsDebuggingEnabled
import android.webkit.WebViewClient
import androidx.activity.ComponentActivity
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Refresh
import androidx.compose.material3.FloatingActionButton
import androidx.compose.material3.Icon
import androidx.compose.material3.Scaffold
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.viewinterop.AndroidView
import androidx.core.app.ActivityCompat
import com.example.bachelorproject.ui.theme.BachelorProjectTheme
import org.json.JSONObject
import java.io.ByteArrayOutputStream
import java.util.concurrent.CountDownLatch
import java.util.concurrent.TimeUnit

val PERMISSIONS = arrayOf(
    Manifest.permission.CAMERA,
)

class Bridge(
    private val context: Context,
    private val onPermissionRequest: () -> Unit,
    private val onTakePhoto: (callback: (String?) -> Unit) -> Unit
) {
    @JavascriptInterface
    fun hello(name: String): String {
        return "Hello $name from Android!"
    }

    @JavascriptInterface
    fun requestPermissions() {
        onPermissionRequest()
    }

    @JavascriptInterface
    fun takePhoto(): String? {
        if (ActivityCompat.checkSelfPermission(context, Manifest.permission.CAMERA) != PackageManager.PERMISSION_GRANTED) {
            return null
        }

        val latch = CountDownLatch(1)
        var photoBase64: String? = null

        Handler(Looper.getMainLooper()).post {
            onTakePhoto { result ->
                photoBase64 = result
                latch.countDown()
            }
        }

        try {
            latch.await(60, TimeUnit.SECONDS)
        } catch (e: InterruptedException) {
            Log.e("Bridge", "Photo capture interrupted", e)
        }

        return photoBase64
    }

    @JavascriptInterface
    fun getPermissionStatus(): String {
        val permissions = PERMISSIONS

        val result = JSONObject()
        for (permission in permissions) {
            val isGranted = ActivityCompat.checkSelfPermission(context, permission) == PackageManager.PERMISSION_GRANTED
            result.put(permission, isGranted)
        }

        return result.toString()
    }

//    @JavascriptInterface
//    fun gps(): String? {
//        val fusedLocationClient = LocationServices.getFusedLocationProviderClient(context)
//
//        // Check permissions
//        if (ActivityCompat.checkSelfPermission(
//                context,
//                Manifest.permission.ACCESS_FINE_LOCATION
//            ) != PackageManager.PERMISSION_GRANTED &&
//            ActivityCompat.checkSelfPermission(
//                context,
//                Manifest.permission.ACCESS_COARSE_LOCATION
//            ) != PackageManager.PERMISSION_GRANTED
//        ) {
//            return "ERROR"
//        }
//
//        return try {
//            val location = Tasks.await(fusedLocationClient.lastLocation)
//            location?.let { "${it.latitude},${it.longitude}" }
//        } catch (e: Exception) {
//            Log.e("Bridge", "Error getting location", e)
//            null
//        }
//    }
}

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()

        val url: String = System.getenv("URL") ?: "http://localhost:5173/";

        setContent {
            BachelorProjectTheme {
                val permissionLauncher = rememberLauncherForActivityResult(
                    ActivityResultContracts.RequestMultiplePermissions()
                ) { permissions ->
                    Log.d("Permissions", permissions.toString());
                }

                var photoCallback by remember { mutableStateOf<((String?) -> Unit)?>(null) }
                val takePhotoLauncher = rememberLauncherForActivityResult(
                    ActivityResultContracts.TakePicturePreview()
                ) { bitmap ->
                    if (bitmap != null) {
                        val outputStream = ByteArrayOutputStream()
                        bitmap.compress(Bitmap.CompressFormat.JPEG, 100, outputStream)
                        val byteArray = outputStream.toByteArray()
                        val base64 = Base64.encodeToString(byteArray, Base64.NO_WRAP)
                        photoCallback?.invoke(base64)
                    } else {
                        photoCallback?.invoke(null)
                    }
                    photoCallback = null
                }

                WebViewScreen(
                    url = url,
                    onPermissionRequest = {
                        permissionLauncher.launch(PERMISSIONS)
                    },
                    onTakePhoto = { callback ->
                        photoCallback = callback
                        takePhotoLauncher.launch(null)
                    }
                )
            }
        }
    }
}

@Composable
fun WebViewScreen(
    url: String,
    onPermissionRequest: () -> Unit,
    onTakePhoto: (callback: (String?) -> Unit) -> Unit
) {
    var webView by remember { mutableStateOf<WebView?>(null) }

    Scaffold(
        floatingActionButton = {
            FloatingActionButton(onClick = { webView?.reload() }) {
                Icon(Icons.Default.Refresh, contentDescription = "Reload")
            }
        }
    ) { paddingValues ->
        AndroidView(
            modifier = Modifier
                .fillMaxSize()
                .padding(paddingValues),
            factory = { context ->
                WebView(context).apply {
                    val pkg = getCurrentWebViewPackage()
                    Log.d("WebView", "WebView provider: ${pkg?.packageName} ${pkg?.versionName}")

                    settings.domStorageEnabled = true
                    settings.javaScriptEnabled = true
                    settings.allowFileAccess = true
                    settings.allowContentAccess = true
                    settings.allowFileAccessFromFileURLs = true
                    settings.allowUniversalAccessFromFileURLs = true

                    setWebContentsDebuggingEnabled(true)
                    webViewClient = WebViewClient()
                    webChromeClient = WebChromeClient()
                    addJavascriptInterface(Bridge(context, onPermissionRequest, onTakePhoto), "native")

                    loadUrl(url)
                }.also { webView = it }
            }
        )
    }
}
