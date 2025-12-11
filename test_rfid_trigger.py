"""Tests for rfid_trigger.py AuthorizedCards class."""

import json
import pytest
from pathlib import Path
from rfid_trigger import AuthorizedCards


@pytest.fixture
def temp_config(tmp_path):
    """Create a temporary config file path."""
    return tmp_path / "authorized_cards.json"


class TestAuthorizedCardsLoad:
    """Tests for loading config files."""

    def test_load_new_format_with_names(self, temp_config):
        """Load config with new dict format (card_id -> name)."""
        temp_config.parent.mkdir(parents=True, exist_ok=True)
        temp_config.write_text(json.dumps({
            "authorized_cards": {
                "ABC123": "Wei's Phone",
                "DEF456": "Backup Card"
            }
        }))

        auth = AuthorizedCards(temp_config)

        assert len(auth.cards) == 2
        assert auth.cards["ABC123"] == "Wei's Phone"
        assert auth.cards["DEF456"] == "Backup Card"

    def test_load_old_format_list(self, temp_config):
        """Load config with old list format (backward compatibility)."""
        temp_config.parent.mkdir(parents=True, exist_ok=True)
        temp_config.write_text(json.dumps({
            "authorized_cards": ["ABC123", "DEF456"]
        }))

        auth = AuthorizedCards(temp_config)

        assert len(auth.cards) == 2
        assert auth.cards["ABC123"] == ""
        assert auth.cards["DEF456"] == ""

    def test_load_nonexistent_file(self, temp_config):
        """Load from nonexistent file creates empty cards."""
        auth = AuthorizedCards(temp_config)
        assert len(auth.cards) == 0

    def test_load_empty_config(self, temp_config):
        """Load empty authorized_cards list."""
        temp_config.parent.mkdir(parents=True, exist_ok=True)
        temp_config.write_text(json.dumps({"authorized_cards": []}))

        auth = AuthorizedCards(temp_config)
        assert len(auth.cards) == 0


class TestAuthorizedCardsAdd:
    """Tests for adding cards."""

    def test_add_card_with_name(self, temp_config):
        """Add a card with a name."""
        auth = AuthorizedCards(temp_config)
        auth.add("ABC123", "Wei's Phone")

        assert "ABC123" in auth.cards
        assert auth.cards["ABC123"] == "Wei's Phone"

    def test_add_card_without_name(self, temp_config):
        """Add a card without a name."""
        auth = AuthorizedCards(temp_config)
        auth.add("ABC123")

        assert "ABC123" in auth.cards
        assert auth.cards["ABC123"] == ""

    def test_add_card_updates_existing(self, temp_config):
        """Adding existing card updates its name."""
        auth = AuthorizedCards(temp_config)
        auth.add("ABC123", "Old Name")
        auth.add("ABC123", "New Name")

        assert auth.cards["ABC123"] == "New Name"

    def test_add_card_persists(self, temp_config):
        """Added card is persisted to config file."""
        auth = AuthorizedCards(temp_config)
        auth.add("ABC123", "Test Card")

        # Reload from file
        auth2 = AuthorizedCards(temp_config)
        assert "ABC123" in auth2.cards
        assert auth2.cards["ABC123"] == "Test Card"


class TestAuthorizedCardsRemove:
    """Tests for removing cards."""

    def test_remove_existing_card(self, temp_config):
        """Remove an existing card."""
        auth = AuthorizedCards(temp_config)
        auth.add("ABC123", "Test Card")
        auth.remove("ABC123")

        assert "ABC123" not in auth.cards

    def test_remove_nonexistent_card(self, temp_config, capsys):
        """Remove nonexistent card prints warning."""
        auth = AuthorizedCards(temp_config)
        auth.remove("NOTFOUND")

        captured = capsys.readouterr()
        assert "Card not found" in captured.out

    def test_remove_persists(self, temp_config):
        """Removed card is persisted to config file."""
        auth = AuthorizedCards(temp_config)
        auth.add("ABC123", "Test Card")
        auth.remove("ABC123")

        # Reload from file
        auth2 = AuthorizedCards(temp_config)
        assert "ABC123" not in auth2.cards


class TestAuthorizedCardsQuery:
    """Tests for querying cards."""

    def test_is_authorized_true(self, temp_config):
        """is_authorized returns True for authorized card."""
        auth = AuthorizedCards(temp_config)
        auth.add("ABC123")

        assert auth.is_authorized("ABC123") is True

    def test_is_authorized_false(self, temp_config):
        """is_authorized returns False for unauthorized card."""
        auth = AuthorizedCards(temp_config)

        assert auth.is_authorized("NOTFOUND") is False

    def test_get_name_with_name(self, temp_config):
        """get_name returns the card name."""
        auth = AuthorizedCards(temp_config)
        auth.add("ABC123", "Wei's Phone")

        assert auth.get_name("ABC123") == "Wei's Phone"

    def test_get_name_without_name(self, temp_config):
        """get_name returns empty string for card without name."""
        auth = AuthorizedCards(temp_config)
        auth.add("ABC123")

        assert auth.get_name("ABC123") == ""

    def test_get_name_nonexistent(self, temp_config):
        """get_name returns empty string for nonexistent card."""
        auth = AuthorizedCards(temp_config)

        assert auth.get_name("NOTFOUND") == ""

    def test_get_display_name_with_name(self, temp_config):
        """get_display_name returns 'CARD_ID (Name)' format."""
        auth = AuthorizedCards(temp_config)
        auth.add("ABC123", "Wei's Phone")

        assert auth.get_display_name("ABC123") == "ABC123 (Wei's Phone)"

    def test_get_display_name_without_name(self, temp_config):
        """get_display_name returns just card ID when no name."""
        auth = AuthorizedCards(temp_config)
        auth.add("ABC123")

        assert auth.get_display_name("ABC123") == "ABC123"


class TestAuthorizedCardsList:
    """Tests for listing cards."""

    def test_list_cards_with_names(self, temp_config, capsys):
        """list_cards shows cards with names."""
        auth = AuthorizedCards(temp_config)
        auth.add("ABC123", "Wei's Phone")
        auth.add("DEF456", "Backup Card")

        auth.list_cards()
        captured = capsys.readouterr()

        assert "ABC123 (Wei's Phone)" in captured.out
        assert "DEF456 (Backup Card)" in captured.out

    def test_list_cards_without_names(self, temp_config, capsys):
        """list_cards shows cards without names."""
        auth = AuthorizedCards(temp_config)
        auth.add("ABC123")

        auth.list_cards()
        captured = capsys.readouterr()

        assert "ABC123" in captured.out
        assert "()" not in captured.out

    def test_list_cards_empty(self, temp_config, capsys):
        """list_cards shows message when no cards."""
        auth = AuthorizedCards(temp_config)

        auth.list_cards()
        captured = capsys.readouterr()

        assert "No authorized cards" in captured.out


class TestConfigFileSave:
    """Tests for config file format."""

    def test_save_new_format(self, temp_config):
        """Config is saved in new dict format."""
        auth = AuthorizedCards(temp_config)
        auth.add("ABC123", "Test Card")

        data = json.loads(temp_config.read_text())

        assert isinstance(data["authorized_cards"], dict)
        assert data["authorized_cards"]["ABC123"] == "Test Card"
