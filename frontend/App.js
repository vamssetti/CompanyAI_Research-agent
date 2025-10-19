import React, { useState, useEffect } from "react";
import {
  StyleSheet,
  Text,
  View,
  TextInput,
  TouchableOpacity,
  ActivityIndicator,
  FlatList,
  Modal,
  Alert,
  KeyboardAvoidingView,
  Platform,
  Keyboard,
} from "react-native";
import { GoogleSignin, statusCodes } from "@react-native-google-signin/google-signin";

// 🔗 Replace with your backend URL
const BACKEND_URL = "https://southbound-abbie-unprotestingly.ngrok-free.dev/chat";

export default function App() {
  const [message, setMessage] = useState("");
  const [chat, setChat] = useState([]);
  const [loading, setLoading] = useState(false);
  const [user, setUser] = useState(null);
  const [showDashboard, setShowDashboard] = useState(false);

  useEffect(() => {
    GoogleSignin.configure({
      webClientId: "42550855283-vppdb6isl5uq2v0epap14k9lishnml6b.apps.googleusercontent.com",
      offlineAccess: true,
    });

    // Optional: Debug keyboard events
    const show = Keyboard.addListener("keyboardDidShow", () => console.log("Keyboard shown"));
    const hide = Keyboard.addListener("keyboardDidHide", () => console.log("Keyboard hidden"));
    return () => {
      show.remove();
      hide.remove();
    };
  }, []);

  const signInWithGoogle = async () => {
    try {
      await GoogleSignin.hasPlayServices();
      const userInfo = await GoogleSignin.signIn();
      setUser(userInfo);
      console.log("User signed in:", userInfo);
    } catch (error) {
      if (error.code === statusCodes.SIGN_IN_CANCELLED) {
        console.log("Sign in cancelled");
        Alert.alert("Sign-In Cancelled", "You cancelled the sign-in process.");
      } else if (error.code === statusCodes.IN_PROGRESS) {
        console.log("Sign in in progress");
      } else if (error.code === statusCodes.PLAY_SERVICES_NOT_AVAILABLE) {
        console.log("Play services not available");
        Alert.alert("Error", "Google Play Services is not available on this device.");
      } else {
        console.error("Sign in error:", error);
        Alert.alert("Error", "An error occurred during sign-in. Please try again.");
      }
    }
  };

  const sendMessage = async () => {
    if (!message.trim()) return;
    const userMsg = { role: "user", content: message };
    setChat((prev) => [...prev, userMsg]);
    setMessage("");
    setLoading(true);

    try {
      const res = await fetch(BACKEND_URL, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ thread_id: "default", message }),
      });
      const data = await res.json();
      const botMsg = { role: "assistant", content: data.response || "No reply received." };
      setChat((prev) => [...prev, botMsg]);
    } catch (error) {
      setChat((prev) => [
        ...prev,
        { role: "assistant", content: "Error connecting to backend." },
      ]);
    }
    setLoading(false);
  };

  // Original action buttons with icons
  const actions = [
    { title: "Schedule a meet", example: "Schedule a meeting for tomorrow at 3 PM", icon: "📅", iconColor: "#0d6efd" },
    { title: "Mail a person", example: "Send an email to John about meeting", icon: "📧", iconColor: "#0d6efd" },
    { title: "Know about a company", example: "Tell me about ABC Corp", icon: "🔍", iconColor: "#0d6efd" },
    { title: "Plan your business trip", example: "Plan a trip from Tokyo to Osaka", icon: "✈️", iconColor: "#0d6efd" },
  ];

  const handleActionPress = (example) => {
    if (example) {
      setMessage(example);
    } else {
      console.log("Show more options");
    }
  };

  const openDashboard = () => {
    if (!user) {
      Alert.alert("Sign-In Required", "Please sign up first to access the dashboard.");
      return;
    }
    setShowDashboard(true);
  };

  return (
    <KeyboardAvoidingView
      style={styles.flexContainer}
      behavior={Platform.OS === "ios" ? "padding" : "height"}
      keyboardVerticalOffset={Platform.OS === "ios" ? 0 : 50} // Reduced from 100 to minimize space
    >
      <View style={styles.container}>
        {/* Header */}
        <View style={styles.header}>
          <TouchableOpacity onPress={openDashboard}>
            <Text style={styles.menuIcon}>≡</Text>
          </TouchableOpacity>
          <Text style={styles.title}>AgentAI</Text>
          <TouchableOpacity style={styles.signUpButton} onPress={signInWithGoogle}>
            <Text style={styles.signUpText}>Sign up with Google</Text>
          </TouchableOpacity>
        </View>

        {/* Greeting */}
        <Text style={styles.greeting}>What can I help with?</Text>

        {/* Action Buttons */}
        <View style={styles.buttonsContainer}>
          {actions.map((action, index) => (
            <TouchableOpacity
              key={index}
              style={styles.button}
              onPress={() => handleActionPress(action.example)}
            >
              <Text style={[styles.buttonIcon, { color: action.iconColor || "#58a6ff" }]}>
                {action.icon}
              </Text>
              <Text style={styles.buttonTitle}>{action.title}</Text>
            </TouchableOpacity>
          ))}
        </View>

        {/* Chat Area */}
        <FlatList
          style={styles.chatContainer}
          data={chat}
          keyExtractor={(item, index) => index.toString()}
          renderItem={({ item }) => (
            <View
              style={[
                styles.messageBubble,
                item.role === "user" ? styles.userBubble : styles.botBubble,
              ]}
            >
              <Text style={item.role === "user" ? styles.userText : styles.botText}>
                {item.content}
              </Text>
            </View>
          )}
          ListFooterComponent={loading && <ActivityIndicator size="small" color="#555" />}
        />

        {/* Input Area */}
        <View style={styles.inputContainer}>
          <TextInput
            style={styles.input}
            placeholder="Ask anything..."
            placeholderTextColor="#999"
            value={message}
            onChangeText={setMessage}
          />
          <TouchableOpacity style={styles.inputIcon}>
            <Text>🎤</Text>
          </TouchableOpacity>
          <TouchableOpacity style={styles.sendButton} onPress={sendMessage}>
            <Text style={styles.buttonText}>Send</Text>
          </TouchableOpacity>
        </View>

        {/* Dashboard Modal */}
        <Modal
          visible={showDashboard}
          onRequestClose={() => setShowDashboard(false)}
          animationType="slide"
        >
          <View style={styles.dashboardContainer}>
            <Text style={styles.dashboardTitle}>Dashboard</Text>
            <Text style={styles.dashboardText}>
              Welcome, {user && user.user ? user.user.name : "Guest"}!
            </Text>
            <Text style={styles.dashboardText}>
              Your email: {user && user.user ? user.user.email : "Not signed in"}
            </Text>
            {user ? (
              <TouchableOpacity
                style={styles.closeButton}
                onPress={() => {
                  setUser(null);
                  setShowDashboard(false);
                }}
              >
                <Text style={styles.closeButtonText}>Logout</Text>
              </TouchableOpacity>
            ) : null}
            <TouchableOpacity
              style={styles.closeButton}
              onPress={() => setShowDashboard(false)}
            >
              <Text style={styles.closeButtonText}>Close</Text>
            </TouchableOpacity>
          </View>
        </Modal>
      </View>
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  flexContainer: {
    flex: 1, // Ensures full screen height
  },
  container: {
    flex: 1,
    backgroundColor: "#0d1117",
    paddingTop: 50,
    paddingHorizontal: 10,
  },
  header: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    marginBottom: 20,
  },
  menuIcon: {
    fontSize: 24,
    color: "#fff",
  },
  title: {
    fontSize: 20,
    fontWeight: "bold",
    color: "#fff",
  },
  signUpButton: {
    backgroundColor: "#fff",
    paddingVertical: 6,
    paddingHorizontal: 12,
    borderRadius: 20,
  },
  signUpText: {
    color: "#000",
    fontWeight: "bold",
  },
  greeting: {
    fontSize: 24,
    color: "#fff",
    textAlign: "center",
    marginBottom: 20,
  },
  buttonsContainer: {
    flexDirection: "row",
    flexWrap: "wrap",
    justifyContent: "space-between",
    marginBottom: 20,
  },
  button: {
    flexDirection: "row",
    alignItems: "center",
    backgroundColor: "#21262d",
    paddingVertical: 12,
    paddingHorizontal: 16,
    borderRadius: 20,
    marginBottom: 10,
    width: "48%",
  },
  buttonIcon: {
    fontSize: 16,
    marginRight: 8,
  },
  buttonTitle: {
    color: "#58a6ff",
    fontSize: 14,
  },
  chatContainer: {
    flex: 1,
    marginVertical: 10,
  },
  messageBubble: {
    borderRadius: 10,
    marginVertical: 4,
    padding: 10,
    maxWidth: "85%",
  },
  userBubble: {
    alignSelf: "flex-end",
    backgroundColor: "#238636",
  },
  botBubble: {
    alignSelf: "flex-start",
    backgroundColor: "#161b22",
    borderWidth: 1,
    borderColor: "#30363d",
  },
  userText: {
    color: "white",
  },
  botText: {
    color: "#c9d1d9",
  },
  inputContainer: {
    flexDirection: "row",
    alignItems: "center",
    paddingVertical: 10,
    backgroundColor: "#0d1117",
  },
  inputIcon: {
    marginHorizontal: 8,
    fontSize: 20,
    color: "#999",
  },
  input: {
    flex: 1,
    backgroundColor: "#161b22",
    color: "white",
    padding: 10,
    borderRadius: 20,
    borderWidth: 1,
    borderColor: "#30363d",
  },
  sendButton: {
    marginLeft: 8,
    backgroundColor: "#238636",
    paddingVertical: 10,
    paddingHorizontal: 16,
    borderRadius: 20,
  },
  buttonText: {
    color: "white",
    fontWeight: "bold",
  },
  dashboardContainer: {
    flex: 1,
    backgroundColor: "#0d1117",
    justifyContent: "center",
    alignItems: "center",
    padding: 20,
  },
  dashboardTitle: {
    fontSize: 28,
    color: "#fff",
    marginBottom: 20,
  },
  dashboardText: {
    fontSize: 18,
    color: "#c9d1d9",
    marginBottom: 10,
  },
  closeButton: {
    backgroundColor: "#238636",
    paddingVertical: 10,
    paddingHorizontal: 20,
    borderRadius: 20,
    marginTop: 20,
  },
  closeButtonText: {
    color: "white",
    fontWeight: "bold",
  },
});
