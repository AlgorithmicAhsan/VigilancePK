import stanza
import re

class UrduProcessor:
    def __init__(self):
        # 1. Download the Urdu model (only happens once)
        print("Initializing Stanza Urdu model... (this may take a minute first time)")
        try:
            stanza.download('ur', processors='tokenize,lemma,pos', logging_level='WARN')
        except Exception as e:
            print(f"Download failed: {e}. If you are offline, ensure models are pre-downloaded.")
        
        # 2. Build the pipeline
        # We use tokenize (normalization), lemma (roots), and pos (parts of speech)
        self.nlp = stanza.Pipeline('ur', processors='tokenize,lemma,pos', use_gpu=True, logging_level='WARN')

    def is_urdu(self, text):
        """Detects if text contains Urdu/Arabic script characters."""
        if not text:
            return False
        # Urdu/Arabic script range
        return any('\u0600' <= char <= '\u06ff' for char in text)

    def normalize_text(self, text):
        """Uses Stanza's professional tokenizer and processor to normalize Urdu."""
        if not text or not self.is_urdu(text):
            return text
        
        doc = self.nlp(text)
        
        # Stanza's tokenizer already handles basic normalization.
        # We can extract the 'text' from processed tokens which are standardized.
        tokens = [word.text for sent in doc.sentences for word in sent.words]
        return " ".join(tokens)

    def get_lemmas(self, text):
        """Extracts the root forms of words (useful for better search/classification)."""
        if not text or not self.is_urdu(text):
            return []
            
        doc = self.nlp(text)
        lemmas = [word.lemma for sent in doc.sentences for word in sent.words]
        return lemmas

    def process_article(self, article):
        """Enriches an article with language detection and normalization."""
        title = article.get('title', '')
        summary = article.get('summary', '')
        
        if self.is_urdu(title) or self.is_urdu(summary):
            article['language'] = 'urdu'
            article['title_norm'] = self.normalize_text(title)
            article['summary_norm'] = self.normalize_text(summary)
            article['ur_lemmas'] = self.get_lemmas(title) + self.get_lemmas(summary)
        else:
            article['language'] = 'english'
            
        return article

if __name__ == "__main__":
    # Professional Test Suite
    processor = UrduProcessor()
    
    # Example Urdu sentence with mixed fonts/forms
    test_urdu = "یہ ایک اُردو ٹیسٹ ہے جس ميں مختلف فونٹس استعمال ہوئے ہيں"
    
    print("\n--- Stanza Urdu Processing ---")
    print(f"Original: {test_urdu}")
    
    if processor.is_urdu(test_urdu):
        normalized = processor.normalize_text(test_urdu)
        lemmas = processor.get_lemmas(test_urdu)
        
        print(f"Normalized: {normalized}")
        print(f"Lemmas (Roots): {lemmas}")
    else:
        print("Text not identified as Urdu.")
