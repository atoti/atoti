from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, List, Mapping, Literal, Optional, Union
from atoti import Level, Session, NaturalOrder, CustomOrder
from atoti.type import STRING

# from atoti._exceptions import AtotiException


@dataclass(frozen=True)
class ContextLevel:
    """
    Attributes
        level: Level require for the action to be displayed.
        display_in_context: Display the value of this level selected in the Context section of the drawer.
    """

    level: Level
    required: bool = False
    display_in_context: bool = True


class CallBackResultFormat:
    levels: Mapping[str, List[any]]
    inputs: Mapping[str, List[any]]


@dataclass
class AsyncOptions:
    """
    Attributes
        callback: function that will be called on action opened and on any input change to retrieve list of options for this input.
            Three arguments will be passed to this callback:
                - session
                - Result containing dictionnary of levels values and inputs values.
            It should return a list of options.
        levels: List of levels passed to the call back function.
        input_fields: List of input fields this option callback will listen to.
    """

    callback: Callable[[Session, CallBackResultFormat], List[any]]
    levels: Optional[List[ContextLevel]] = field(default_factory=list)
    input_fields: Optional[List[InputField]] = field(default_factory=list)


@dataclass(frozen=True)
class InputField:
    """

    Attributes
        name: Name of the field user will enter in the form.
        input_type: Helper for user to enter correct data. (Date incoming).
        default_from_level: If the default value is taken from a level.
        /!\\ This level must be in the required level list.
        options: List of options that user can choose to fill faster values. User can still enter another value
        that is not on the list.
    """

    name: str
    input_type: Literal["number", "string", "date"]
    default_from_level: Optional[Level] = None
    options: Union[List[any], Optional[AsyncOptions]] = field(default_factory=list)


@dataclass
class Action:
    action_name: str
    context_levels: List[ContextLevel]
    action: Callable[[Session, List[ContextLevel], Mapping[str, any]], None]
    success_message: Optional[str] = "Created action"
    error_message: Optional[str] = "Something went wrong"
    action_id: Optional[int] = None
    has_drawer: bool = False


@dataclass
class ClassificationLevel:
    table_name: str
    field_name: str
    field_type: str
    dimension_name: str
    hierarchy_name: str
    level_name: str


class DynamicClassification:
    def __init__(
        self,
        level: Level,
        classification_level_name: str,
        classification_order: NaturalOrder | CustomOrder = None,
        default_classification_member: str = "All"
        # context_levels:List[DynamicClassificationLevel] = None
    ):
        self.level = level
        self.classification_level = ClassificationLevel(
            level._column_identifier.table_identifier.table_name,
            level._column_identifier.column_name,
            level.data_type,
            level.dimension,
            level.hierarchy,
            level.name,
        )
        self.classification_group_level = ClassificationLevel(
            f"{level.name}_{classification_level_name}",
            classification_level_name,
            STRING,
            level.dimension,
            classification_level_name,
            classification_level_name,
        )
        if classification_order is None:
            self.order = level.order
        self.default_classification_member = default_classification_member


class DrawerAction(Action):
    """
    Attributes:
        action_name: Name of the action that will appear on the context menu.
        drawer_title: Title of the drawer that will appear on the right after clicking on action.
        required_levels: List of levels required so that action appears to user.
        input_fields: List of inputs that user will need to fill in order to perform the action.
        action: Call back once the user submit its form. It will retrieve a map containing both inputs and all required fields.
        optional_levels: List of levels that, if info exist, will be added to the callback.
        success_message: Message displayed to user if submit has passed.
        error_message: Message displayed to user if something goes wrong.
        size: size of the drawer.
    """

    drawer_title: str
    input_fields: List[InputField]
    has_drawer: bool = True
    size: Literal["small", "large"]

    def __init__(
        self,
        action_name: str,
        drawer_title: str,
        context_levels: List[ContextLevel],
        input_fields: List[InputField],
        action: Callable[[Session, List[ContextLevel], Mapping[str, any]], None],
        success_message="Created action",
        error_message="Something went wrong",
        size: Literal["small", "large"] = "small",
    ):
        self.action_name = action_name
        self.context_levels = context_levels
        self.action = action
        self.success_message = success_message
        self.error_message = error_message
        self.drawer_title = drawer_title
        self.input_fields = input_fields
        self.size = size


class ActionGenerator:
    _session: Session
    _actions: Mapping[str, Action | DrawerAction]
    _dynamic_classifications: List[DynamicClassification]
    _id: int
    _global_name: str

    def __init__(self, session, global_name="Actions:"):
        self._session = session
        self._id = 0
        self._global_name = global_name
        self._actions = {}
        self._dynamic_classifications = []
        self._generate_endpoints()

    def create_new_action(self, action: Action) -> int:
        """
        Create a new action that will be available in the UI context menu.

        :param action: Action object to add.
        :return: the id of the action created, usefull to edit or remove it.
        """
        self._id = self._id + 1
        action.action_id = f"{self._id}"
        self._actions[f"{self._id}"] = action
        return f"{self._id}"

    def add_new_dynamic_classification(
        self, dynamic_classification: DynamicClassification
    ) -> None:
        level_name = dynamic_classification.classification_level.level_name
        classification_level_name = (
            dynamic_classification.classification_group_level.level_name
        )
        new_table_name = dynamic_classification.classification_group_level.table_name
        if new_table_name in self._session.tables:
            print(
                f"The table {new_table_name} has already be create for this level {level_name} and classification name : {classification_level_name}"
            )
            return None
        cube = self._session.cubes[dynamic_classification.level._cube_name]
        new_table = self._session.create_table(
            keys=[level_name],
            types={
                level_name: dynamic_classification.classification_level.field_type,
                classification_level_name: dynamic_classification.classification_group_level.field_type,
            },
            default_values={
                classification_level_name: dynamic_classification.default_classification_member
            },
            name=new_table_name,
        )
        self._session.tables[
            dynamic_classification.classification_level.table_name
        ].join(new_table)
        if classification_level_name in cube.levels:
            del cube.levels[classification_level_name]
        cube.hierarchies[
            (
                dynamic_classification.classification_group_level.dimension_name,
                dynamic_classification.classification_group_level.hierarchy_name,
            )
        ] = {classification_level_name: new_table[classification_level_name]}
        if dynamic_classification.order is not None:
            cube.levels[classification_level_name].order = dynamic_classification.order

        self._dynamic_classifications.append(dynamic_classification)

    def remove_action(self, action_id: str) -> None:
        """
        Remove an existing action by passing its id.
        Raise an exception if the id is not found.

        :param action_id: Id of the action to remove.
        """
        if action_id in self._actions:
            del self._actions[action_id]
        else:
            raise AtotiException(
                f"This action ID: {action_id} has already been deleted or not been created yet."
            )

    def update_action(self, action_id: str, action: Action | DrawerAction) -> int:
        """
        Update the action by passing a new action object and its id.
        Raise an exception if the id is not found.

        :param action_id: Id of an existing action.
        :param action: Action to pass to update.
        :return: the id of the updated action.
        """
        if action_id in self._actions:
            self._actions[action_id] = action
            return action_id
        raise AtotiException(
            f"This action ID: {action_id} has already been deleted or not been created yet."
        )

    def _generate_endpoints(self):
        @self._session.endpoint("actions", method="GET")
        def _get_actions(request, user, session):
            return {
                "globalTitle": self._global_name,
                "actions": [
                    {
                        "id": action.action_id,
                        "name": action.action_name,
                        "contextLevels": [
                            {
                                "dimensionName": rl.level.dimension,
                                "hierarchyName": rl.level.hierarchy,
                                "levelName": rl.level.name,
                                "required": rl.required,
                                "displayInContext": rl.display_in_context,
                            }
                            for rl in action.context_levels
                        ],
                        "hasDrawer": action.has_drawer,
                        "successMessage": action.success_message,
                        "errorMessage": action.error_message,
                    }
                    for action in self._actions.values()
                ],
            }

        @self._session.endpoint("action/{id}", method="GET")
        def _get_action(request, user, session):
            id_action = request.path_parameters["id"]
            action: DrawerAction = self._actions[id_action]
            return {
                "popUpName": action.drawer_title,
                "contextLevels": [
                    {
                        "dimensionName": rl.level.dimension,
                        "hierarchyName": rl.level.hierarchy,
                        "levelName": rl.level.name,
                        "required": rl.required,
                        "displayInContext": rl.display_in_context,
                    }
                    for rl in action.context_levels
                ],
                "inputFields": [
                    {
                        "name": i_f.name,
                        "type": i_f.input_type,
                        "defaultFromLevel": {
                            "dimensionName": i_f.default_from_level.dimension,
                            "hierarchyName": i_f.default_from_level.hierarchy,
                            "levelName": i_f.default_from_level.name,
                        }
                        if (str(i_f.default_from_level) != "None")
                        else None,
                        "options": i_f.options if isinstance(i_f.options, List) else [],
                        "asyncOptionsCallback": {
                            "levels": [
                                {
                                    "dimensionName": async_option_level.dimension,
                                    "hierarchyName": async_option_level.hierarchy,
                                    "levelName": async_option_level.name,
                                }
                                for async_option_level in i_f.options.levels
                            ],
                            "inputFieldNames": [
                                i_f_.name for i_f_ in i_f.options.input_fields
                            ],
                        }
                        if isinstance(i_f.options, AsyncOptions)
                        else None,
                    }
                    for i_f in action.input_fields
                ],
                "drawerSize": "378px" if action.size == "small" else "736px",
            }

        @self._session.endpoint("action/execute", method="POST")
        def _execute_actions(request, user, session):
            body = request.body
            action = self._actions[body["id"]]
            action.action(session, body["results"], user)

        @self._session.endpoint("action/options", method="POST")
        def _get_options(request, user, session):
            body = request.body
            action = self._actions[body["id"]]
            if action.has_drawer:
                input_field_name = body["fieldName"]
                for input_field in action.input_fields:
                    if input_field.name == input_field_name:
                        if isinstance(input_field.options, AsyncOptions):
                            return input_field.options.callback(
                                session, body["results"]
                            )
            return []

        @self._session.endpoint("dynamicClassifications", method="GET")
        def _get_dynamic_classifications(request, user, session):
            return [
                {
                    "classificationLevel": {
                        "tableName": d.classification_level.table_name,
                        "fieldName": d.classification_level.field_name,
                        "fieldType": d.classification_level.field_type,
                        "dimensionName": d.classification_level.dimension_name,
                        "hierarchyName": d.classification_level.hierarchy_name,
                        "levelName": d.classification_level.level_name,
                    },
                    "classificationGroupLevel": {
                        "tableName": d.classification_group_level.table_name,
                        "fieldName": d.classification_group_level.field_name,
                        "fieldType": d.classification_group_level.field_type,
                        "dimensionName": d.classification_group_level.dimension_name,
                        "hierarchyName": d.classification_group_level.hierarchy_name,
                        "levelName": d.classification_group_level.level_name,
                    },
                }
                for d in self._dynamic_classifications
            ]
