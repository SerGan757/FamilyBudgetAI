import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from sqlalchemy import inspect
from app.database.models import FamilyCategory, FamilyCategoryKeyword, Transaction
from app.services import custom_category_service as service
from app.services.category_service import detect_category_reference_for_family
from app.i18n import t
from app.i18n.translations import SUPPORTED_LANGUAGES
from app.handlers import categories
from app.keyboards.categories import (
 category_card_keyboard, custom_archive_keyboard, icon_keyboard,
 keyword_pages_keyboard, operations_keyboard, CategoryCallback,
)

def unpack(button):
 return CategoryCallback.unpack(button.callback_data)

class SchemaTests(unittest.TestCase):
 def test_models_and_stable_link(self):
  self.assertEqual(FamilyCategory.__tablename__,"family_categories")
  self.assertEqual(FamilyCategoryKeyword.__tablename__,"family_category_keywords")
  self.assertTrue(Transaction.__table__.c.custom_category_id.nullable)
  self.assertEqual(next(fk for fk in Transaction.__table__.c.custom_category_id.foreign_keys).ondelete,"SET NULL")
 def test_controlled_migration(self):
  sql=(Path(__file__).parents[1]/"docs/migrations/20260812_add_custom_categories.sql").read_text("utf8")
  self.assertIn("CREATE TABLE family_categories",sql);self.assertIn("CREATE TABLE family_category_keywords",sql)
  self.assertIn("custom_category_id",sql);self.assertNotIn("UPDATE transactions",sql)

class ServiceTests(unittest.IsolatedAsyncioTestCase):
 def test_name_normalization(self): self.assertEqual(service.normalize_category_name("  Развлечения  "),"развлечения")
 async def test_detection_custom_and_inactive(self):
  custom=SimpleNamespace(id=17,icon="🎬",name="Развлечения",keywords=[SimpleNamespace(normalized_keyword="кино")])
  with patch.object(service,"list_custom_categories",AsyncMock(return_value=[custom])):
   cat,score=await service.detect_custom_category(1,"кино");self.assertIs(cat,custom);self.assertEqual(score,100)
  with patch.object(service,"list_custom_categories",AsyncMock(return_value=[])):
   self.assertEqual(await service.detect_custom_category(1,"кино"),(None,0))
 async def test_combined_detector_custom_wins_and_system_tie_wins(self):
  custom=SimpleNamespace(id=17,icon="🎬",name="Развлечения")
  with patch("app.services.custom_category_service.detect_custom_category",AsyncMock(return_value=(custom,100))),patch("app.services.category_service.detect_category_for_family",AsyncMock(return_value=("📦","Прочее"))),patch("app.services.category_override_service.get_effective_category_catalog",AsyncMock(return_value={})):
   self.assertEqual(await detect_category_reference_for_family(1,"кино"),("🎬","Развлечения",17))
 async def test_keyword_conflict_system_and_custom_family_scope(self):
  sys={"cafe":[SimpleNamespace(normalized_keyword="кофе")]}
  other=SimpleNamespace(id=2,keywords=[SimpleNamespace(normalized_keyword="кино")])
  with patch.object(service,"get_effective_category_catalog",AsyncMock(return_value=sys)),patch.object(service,"list_custom_categories",AsyncMock(return_value=[other])):
   self.assertEqual(await service._keyword_conflict(7,1,"кофе"),"system:cafe")
   self.assertEqual(await service._keyword_conflict(7,1,"кино"),"custom:2")
 async def test_delete_history_block(self):
  source=__import__('inspect').getsource(service.delete_custom_category)
  self.assertIn("Transaction.family_id==family_id",source);self.assertIn('return "in_use"',source)
 def test_i18n_keys(self):
  for lang in SUPPORTED_LANGUAGES:
   for key in ("custom.mine","custom.new","custom.archive","custom.edit_name","custom.disable","custom.restore","custom.delete","custom.in_use"):
    self.assertNotEqual(t(lang,key),key)
 def test_reserved_names_include_localized_system_labels(self):
  reserved=service._reserved_names()
  self.assertIn("прочее",reserved);self.assertIn("other",reserved);self.assertIn("sonstiges",reserved)

class CategoryUxTests(unittest.IsolatedAsyncioTestCase):
 def callback(self):
  message=SimpleNamespace(
   chat=SimpleNamespace(id=10,type="private"),edit_text=AsyncMock(),message_id=99,
  )
  return SimpleNamespace(message=message,from_user=SimpleNamespace(id=1),answer=AsyncMock())

 def family(self,language="en"):
  return SimpleNamespace(id=7,language=language,temporary_screen_ttl=20)

 async def test_add_keywords_replaces_card_with_prompt_and_only_cancel(self):
  callback=self.callback();state=AsyncMock();data=SimpleNamespace(action="custom_add",key="17",value="settings")
  with patch.object(categories,"_family",AsyncMock(return_value=self.family())):
   await categories.category_callback(callback,data,state)
  state.set_state.assert_awaited_once()
  kwargs=callback.message.edit_text.await_args.kwargs
  self.assertIn("comma",callback.message.edit_text.await_args.args[0].lower())
  self.assertEqual(len(kwargs["reply_markup"].inline_keyboard),1)
  cancel=unpack(kwargs["reply_markup"].inline_keyboard[0][0])
  self.assertEqual((cancel.action,cancel.key),("custom_card","17"))

 async def test_cancel_add_clears_fsm_and_returns_custom_card(self):
  callback=self.callback();state=AsyncMock();data=SimpleNamespace(action="custom_card",key="17",value="settings")
  with patch.object(categories,"_family",AsyncMock(return_value=self.family())),patch.object(categories,"show_custom_category_card",AsyncMock(return_value=True)) as show:
   await categories.category_callback(callback,data,state)
  state.clear.assert_awaited_once();show.assert_awaited_once_with(callback.message,self.family(),17,"settings")

 async def test_edit_icon_opens_shared_picker(self):
  callback=self.callback();state=AsyncMock();data=SimpleNamespace(action="custom_edit_icon",key="17",value="settings")
  with patch.object(categories,"_family",AsyncMock(return_value=self.family())):
   await categories.category_callback(callback,data,state)
  text=callback.message.edit_text.await_args.args[0]
  markup=callback.message.edit_text.await_args.kwargs["reply_markup"]
  self.assertEqual(text,t("en","custom.choose_icon"))
  self.assertEqual(markup.model_dump(),icon_keyboard("en","settings","17").model_dump())
  self.assertNotEqual(text,t("en","custom.enter_icon"))

 async def test_ready_icon_updates_only_icon_and_returns_card(self):
  callback=self.callback();state=AsyncMock();data=SimpleNamespace(action="custom_icon",key="17",value="settings|🎬")
  updated=SimpleNamespace(status="updated")
  with patch.object(categories,"_family",AsyncMock(return_value=self.family())),patch.object(categories,"update_custom_category",AsyncMock(return_value=updated)) as update,patch.object(categories,"show_custom_category_card",AsyncMock(return_value=True)) as show:
   await categories.category_callback(callback,data,state)
  update.assert_awaited_once_with(7,17,icon="🎬")
  show.assert_awaited_once_with(callback.message,self.family(),17,"settings")

 async def test_other_emoji_has_cancel_back_to_picker(self):
  callback=self.callback();state=AsyncMock();data=SimpleNamespace(action="custom_other_icon",key="17",value="settings")
  with patch.object(categories,"_family",AsyncMock(return_value=self.family())):
   await categories.category_callback(callback,data,state)
  kwargs=callback.message.edit_text.await_args.kwargs
  cancel=unpack(kwargs["reply_markup"].inline_keyboard[0][0])
  self.assertEqual((cancel.action,cancel.key,cancel.value),("custom_icon_picker","17","settings"))

 async def test_manual_icon_cancel_returns_picker_without_change(self):
  callback=self.callback();state=AsyncMock();data=SimpleNamespace(action="custom_icon_picker",key="17",value="settings")
  with patch.object(categories,"_family",AsyncMock(return_value=self.family())),patch.object(categories,"update_custom_category",AsyncMock()) as update:
   await categories.category_callback(callback,data,state)
  update.assert_not_awaited()
  self.assertEqual(callback.message.edit_text.await_args.args[0],t("en","custom.choose_icon"))

 def test_custom_keyword_back_uses_custom_namespace(self):
  entries=[SimpleNamespace(keyword="netflix")]
  keyboard=keyword_pages_keyboard("custom_remove","17",entries,0,"en","settings")
  back=unpack(keyboard.inline_keyboard[-1][0])
  self.assertEqual((back.action,back.key,back.value),("custom_card","17","settings"))

 def test_archive_has_back_to_category_list(self):
  keyboard=custom_archive_keyboard([],"en","settings")
  back=unpack(keyboard.inline_keyboard[-1][0])
  self.assertEqual((back.action,back.value),("list","settings"))

 def test_custom_operations_back_returns_to_custom_card(self):
  keyboard=operations_keyboard("17",2026,8,0,0,"en","settings")
  back=unpack(keyboard.inline_keyboard[-1][0])
  self.assertEqual((back.action,back.key,back.value),("custom_card","17","settings"))

 def test_new_prompt_navigation_keys_exist_for_requested_locales(self):
  for language in ("de","uk","en"):
   for key in ("custom.choose_icon","custom.other_icon","custom.enter_icon","category.bulk_title","category.bulk_prompt","nav.back","goal.cancel"):
    self.assertNotEqual(t(language,key),key)

 async def test_system_summary_added_restored_existing_conflict(self):
  items=(
   SimpleNamespace(keyword="new",status="added",conflict_category_key=None),
   SimpleNamespace(keyword="back",status="restored",conflict_category_key=None),
   SimpleNamespace(keyword="old",status="already_exists",conflict_category_key=None),
   SimpleNamespace(keyword="coffee",status="conflict",conflict_category_key="cafe"),
  )
  lines=await categories.keyword_result_summary(self.family(),items,include_restored=True)
  text="\n".join(lines)
  self.assertIn(f"{t('en','category.bulk_added')}: 1",text)
  self.assertIn(f"{t('en','category.bulk_restored')}: 1",text)
  self.assertIn(f"{t('en','category.bulk_existing')}: 1",text)
  self.assertIn(f"{t('en','category.bulk_conflicting')}: 1",text)
  self.assertIn("coffee",text);self.assertIn("Eating out",text)

 async def test_custom_summary_mixed_resolves_system_and_custom_conflicts(self):
  items=[
   ("notebook","added",None),("lessons","already_exists",None),
   ("light","conflict","system:house"),("netflix","conflict","custom:8"),
  ]
  custom=SimpleNamespace(id=8,icon="🎬",name="Entertainment")
  with patch.object(categories,"get_custom_category",AsyncMock(return_value=custom)):
   lines=await categories.keyword_result_summary(self.family(),items,include_restored=False)
  text="\n".join(lines)
  self.assertIn(f"{t('en','category.bulk_added')}: 1",text)
  self.assertNotIn(t('en','category.bulk_restored'),text)
  self.assertIn(f"{t('en','category.bulk_existing')}: 1",text)
  self.assertIn(f"{t('en','category.bulk_conflicting')}: 2",text)
  self.assertIn("light",text);self.assertIn("Home",text)
  self.assertIn("netflix",text);self.assertIn("🎬 Entertainment",text)

 async def test_custom_handler_shows_factual_summary_and_refreshes_card(self):
  message=SimpleNamespace(
   text="notebook, coffee, lessons",chat=SimpleNamespace(id=10,type="private"),
   from_user=SimpleNamespace(id=1),answer=AsyncMock(),
  )
  state=AsyncMock();state.get_data.return_value={"custom_category_id":17,"category_origin":"settings","family_id":7}
  result={"items":[("notebook","added",None),("coffee","conflict","system:cafe"),("lessons","already_exists",None)]}
  with patch.object(categories,"_family",AsyncMock(return_value=self.family())),patch.object(categories,"add_custom_keywords",AsyncMock(return_value=result)),patch.object(categories,"answer_custom_category_card",AsyncMock(return_value=True)) as card:
   await categories.custom_keywords_input(message,state)
  state.clear.assert_awaited_once()
  notice=card.await_args.args[4]
  self.assertIn(f"{t('en','category.bulk_added')}: 1",notice)
  self.assertIn(f"{t('en','category.bulk_existing')}: 1",notice)
  self.assertIn(f"{t('en','category.bulk_conflicting')}: 1",notice)
  self.assertIn("coffee",notice);self.assertIn("Eating out",notice)
  self.assertNotEqual(notice,t("en","custom.keywords_saved"))

if __name__=="__main__":unittest.main()
