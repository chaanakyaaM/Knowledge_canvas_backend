from flask import Flask, request, jsonify
from flask_cors import CORS
import firebase_admin
from firebase_admin import credentials, firestore
import os
from datetime import datetime
import logging
from typing import Dict, List, Any, Optional

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        # logging.StreamHandler(),  # log to console
        logging.FileHandler('app.log')  # log to file
    ]
)
logger = logging.getLogger(__name__)

app = Flask(__name__)
CORS(app)  # Enable CORS for all domains on all routes

# Initialize Firebase Admin SDK
def initialize_firebase():
    """Initialize Firebase Admin SDK with service account credentials"""
    try:
        if not firebase_admin._apps:
            if os.getenv('GOOGLE_APPLICATION_CREDENTIALS'):
                # Use default credentials from environment
                cred = credentials.ApplicationDefault()
            else:
                # Use service account key file
                cred = credentials.Certificate({
                    "type": "service_account",
                    "project_id": os.getenv('FIREBASE_PROJECT_ID'),
                    "private_key_id": os.getenv('FIREBASE_PRIVATE_KEY_ID'),
                    "private_key": os.getenv('FIREBASE_PRIVATE_KEY', ''),
                    "client_email": os.getenv('FIREBASE_CLIENT_EMAIL'),
                    "client_id": os.getenv('FIREBASE_CLIENT_ID'),
                    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                    "token_uri": "https://oauth2.googleapis.com/token",
                })
            
            firebase_admin.initialize_app(cred)
        
        # Get Firestore client
        db = firestore.client()
        logger.info("Firebase initialized successfully")
        return db
    
    except Exception as e:
        logger.error(f"Failed to initialize Firebase: {e}")
        raise

# Initialize Firebase
try:
    db = initialize_firebase()
except Exception as e:
    logger.error(f"Firebase initialization failed: {e}")
    db = None

class FlowDataManager:
    """Manager class for handling ReactFlow data operations"""
    
    def __init__(self, firestore_client):
        self.db = firestore_client
        self.collection_name = 'reactflow_data'
    
    def save_flow_data(self, user_id: str, nodes: List[Dict], edges: List[Dict], theme: str = 'light') -> bool:
        """Save nodes, edges, and theme to Firebase"""
        try:
            doc_ref = self.db.collection(self.collection_name).document(user_id)
            
            data = {
                'nodes': nodes,
                'edges': edges,
                'theme': theme,
                'updated_at': firestore.SERVER_TIMESTAMP,
                'node_count': len(nodes),
                'edge_count': len(edges)
            }
            
            doc_ref.set(data)
            logger.info(f"Flow data saved for user: {user_id}")
            return True
            
        except Exception as e:
            logger.error(f"Error saving flow data: {e}")
            return False
    
    def get_flow_data(self, user_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve flow data from Firebase"""
        try:
            doc_ref = self.db.collection(self.collection_name).document(user_id)
            doc = doc_ref.get()
            
            if doc.exists:
                data = doc.to_dict()
                logger.info(f"Flow data retrieved for user: {user_id}")
                return data
            else:
                logger.info(f"No flow data found for user: {user_id}")
                return None
                
        except Exception as e:
            logger.error(f"Error retrieving flow data: {e}")
            return None
    
    def delete_flow_data(self, user_id: str) -> bool:
        """Delete flow data for a user"""
        try:
            doc_ref = self.db.collection(self.collection_name).document(user_id)
            doc_ref.delete()
            logger.info(f"Flow data deleted for user: {user_id}")
            return True
            
        except Exception as e:
            logger.error(f"Error deleting flow data: {e}")
            return False
    
    def add_node(self, user_id: str, node: Dict) -> bool:
        """Add a single node to existing flow data"""
        try:
            doc_ref = self.db.collection(self.collection_name).document(user_id)
            
            # Add timestamp to node
            node['data']['created_at'] = datetime.now().isoformat()
            
            doc_ref.update({
                'nodes': firestore.ArrayUnion([node]),
                'updated_at': firestore.SERVER_TIMESTAMP
            })
            
            logger.info(f"Node added for user: {user_id}")
            return True
            
        except Exception as e:
            logger.error(f"Error adding node: {e}")
            return False
    
    def remove_node(self, user_id: str, node_id: str) -> bool:
        """Remove a node and associated edges"""
        try:
            flow_data = self.get_flow_data(user_id)
            if not flow_data:
                return False
            
            # Filter out the node and associated edges
            updated_nodes = [n for n in flow_data.get('nodes', []) if n['id'] != node_id]
            updated_edges = [e for e in flow_data.get('edges', []) 
                           if e['source'] != node_id and e['target'] != node_id]
            
            doc_ref = self.db.collection(self.collection_name).document(user_id)
            doc_ref.update({
                'nodes': updated_nodes,
                'edges': updated_edges,
                'updated_at': firestore.SERVER_TIMESTAMP
            })
            
            logger.info(f"Node {node_id} removed for user: {user_id}")
            return True
            
        except Exception as e:
            logger.error(f"Error removing node: {e}")
            return False

# Initialize flow data manager
if db:
    flow_manager = FlowDataManager(db)
else:
    flow_manager = None

# Health check endpoint
@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    return jsonify({
        'status': 'healthy',
        'firebase_connected': db is not None,
        'timestamp': datetime.now().isoformat()
    })

# Save flow data
@app.route('/api/flow/save', methods=['POST'])
def save_flow():
    """Save flow data (nodes, edges, theme) to Firebase"""
    if not flow_manager:
        return jsonify({'error': 'Firebase not initialized'}), 500
    
    try:
        data = request.get_json()
        user_id = data.get('user_id', 'default_user')
        nodes = data.get('nodes', [])
        edges = data.get('edges', [])
        theme = data.get('theme', 'light')
        
        if not isinstance(nodes, list) or not isinstance(edges, list):
            return jsonify({'error': 'Invalid data format'}), 400
        
        success = flow_manager.save_flow_data(user_id, nodes, edges, theme)
        
        if success:
            return jsonify({
                'message': 'Flow data saved successfully',
                'node_count': len(nodes),
                'edge_count': len(edges)
            })
        else:
            return jsonify({'error': 'Failed to save flow data'}), 500
            
    except Exception as e:
        print('error is:',e)
        logger.error(f"Error in save_flow: {e}")
        return jsonify({'error': str(e)}), 500

# Load flow data
@app.route('/api/flow/load/<user_id>', methods=['GET'])
def load_flow(user_id):
    """Load flow data from Firebase"""
    if not flow_manager:
        return jsonify({'error': 'Firebase not initialized'}), 500
    
    try:
        flow_data = flow_manager.get_flow_data(user_id)
        
        if flow_data:
            return jsonify({
                'nodes': flow_data.get('nodes', []),
                'edges': flow_data.get('edges', []),
                'theme': flow_data.get('theme', 'light'),
                'updated_at': flow_data.get('updated_at'),
                'node_count': flow_data.get('node_count', 0),
                'edge_count': flow_data.get('edge_count', 0)
            })
        else:
            return jsonify({
                'nodes': [],
                'edges': [],
                'theme': 'light',
                'message': 'No data found for user'
            })
            
    except Exception as e:
        logger.error(f"Error in load_flow: {e}")
        return jsonify({'error': str(e)}), 500

# Add a single node
@app.route('/api/flow/node', methods=['POST'])
def add_node():
    """Add a single node to the flow"""
    if not flow_manager:
        return jsonify({'error': 'Firebase not initialized'}), 500
    
    try:
        data = request.get_json()
        user_id = data.get('user_id', 'default_user')
        node = data.get('node')
        
        if not node:
            return jsonify({'error': 'Node data required'}), 400
        
        success = flow_manager.add_node(user_id, node)
        
        if success:
            return jsonify({'message': 'Node added successfully'})
        else:
            return jsonify({'error': 'Failed to add node'}), 500
            
    except Exception as e:
        logger.error(f"Error in add_node: {e}")
        return jsonify({'error': str(e)}), 500

# Delete a node
@app.route('/api/flow/node/<user_id>/<node_id>', methods=['DELETE'])
def delete_node(user_id, node_id):
    """Delete a node and its associated edges"""
    if not flow_manager:
        return jsonify({'error': 'Firebase not initialized'}), 500
    
    try:
        success = flow_manager.remove_node(user_id, node_id)
        
        if success:
            return jsonify({'message': 'Node deleted successfully'})
        else:
            return jsonify({'error': 'Failed to delete node'}), 500
            
    except Exception as e:
        logger.error(f"Error in delete_node: {e}")
        return jsonify({'error': str(e)}), 500

# Delete all flow data for a user
@app.route('/api/flow/<user_id>', methods=['DELETE'])
def delete_flow(user_id):
    """Delete all flow data for a user"""
    if not flow_manager:
        return jsonify({'error': 'Firebase not initialized'}), 500
    
    try:
        success = flow_manager.delete_flow_data(user_id)
        
        if success:
            return jsonify({'message': 'Flow data deleted successfully'})
        else:
            return jsonify({'error': 'Failed to delete flow data'}), 500
            
    except Exception as e:
        logger.error(f"Error in delete_flow: {e}")
        return jsonify({'error': str(e)}), 500

# List all users with flow data
@app.route('/api/users', methods=['GET'])
def list_users():
    """Get list of all users with flow data"""
    if not db:
        return jsonify({'error': 'Firebase not initialized'}), 500
    
    try:
        docs = db.collection('reactflow_data').stream()
        users = []
        
        for doc in docs:
            data = doc.to_dict()
            users.append({
                'user_id': doc.id,
                'node_count': data.get('node_count', 0),
                'edge_count': data.get('edge_count', 0),
                'theme': data.get('theme', 'light'),
                'updated_at': data.get('updated_at')
            })
        
        return jsonify({'users': users})
        
    except Exception as e:
        logger.error(f"Error in list_users: {e}")
        return jsonify({'error': str(e)}), 500

# Error handlers
@app.errorhandler(404)
def not_found(error):
    return jsonify({'error': 'Endpoint not found'}), 404

@app.errorhandler(500)
def internal_error(error):
    return jsonify({'error': 'Internal server error'}), 500

if __name__ == '__main__':
    # Check if Firebase is properly initialized
    if not db:
        logger.warning("Firebase not initialized. Server will start but Firebase features will be unavailable.")
    
    # Run the Flask app
    app.run(
        host='0.0.0.0',
        port=int(os.getenv('PORT', 5000)),
        # debug=os.getenv('FLASK_DEBUG', 'False').lower() == 'true'
        debug= True
    )