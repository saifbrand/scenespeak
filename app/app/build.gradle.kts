plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
    id("org.jetbrains.kotlin.plugin.compose")
}

android {
    namespace = "com.saifbrand.scenespeak"
    compileSdk = 34

    defaultConfig {
        applicationId = "com.saifbrand.scenespeak"
        // Fire OS 5 is Android 5.1 (API 22), Fire OS 6 is 7.1 (25), Fire OS 7
        // is 9 (28), Fire OS 8 is 11 (30). This was 28 until Amazon's automated
        // testing reported the Fire TV Stick Gen 2 and Fire TV Stick 4K as
        // non-compatible; nothing in the app needs more than 22.
        minSdk = 22
        targetSdk = 34
        versionCode = 2
        versionName = "1.1"
    }

    buildTypes {
        release {
            // Shrunk with R8 and carrying a lighter copy of the film
            // (src/release/assets), so the APK fits upload limits such as
            // Amazon's automated testing. Signed with the debug key: it is
            // for sideloading and testing, not for a store listing.
            isMinifyEnabled = true
            isShrinkResources = true
            proguardFiles(getDefaultProguardFile("proguard-android-optimize.txt"), "proguard-rules.pro")
            signingConfig = signingConfigs.getByName("debug")
        }
    }
    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
    kotlinOptions {
        jvmTarget = "17"
    }
    buildFeatures {
        compose = true
    }
    packaging {
        resources.excludes += "/META-INF/{AL2.0,LGPL2.1}"
    }
}

dependencies {
    implementation(platform("androidx.compose:compose-bom:2024.10.01"))
    implementation("androidx.compose.ui:ui")
    implementation("androidx.compose.foundation:foundation")
    implementation("androidx.compose.material3:material3")
    implementation("androidx.activity:activity-compose:1.9.3")
    implementation("androidx.lifecycle:lifecycle-runtime-compose:2.8.7")
    implementation("androidx.tv:tv-material:1.0.0")
    implementation("androidx.core:core-ktx:1.13.1")

    implementation("androidx.media3:media3-exoplayer:1.4.1")
    implementation("androidx.media3:media3-ui:1.4.1")

    testImplementation("junit:junit:4.13.2")
    testImplementation("org.json:json:20240303")
}
